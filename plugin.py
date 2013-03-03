###
# Copyright (c) 2011-2012, Mike Mueller <mike.mueller@panopticdev.com>
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#   * Do whatever you want
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED.  IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
###

"""
A Supybot plugin that monitors and interacts with git repositories.

This code is threaded. A separate thread run the potential long-running
replication of remote git repositories to local clones. The rest is handled
by the main thread.

A special case of long-running operation is the creation of new repositories,
This is done in  separate thread. The repository involved in this is not
visible for any other thread until cloning is completed.

The critical sections are:
   - The _Repository instances, locked with an instance attribute lock.
   - The Repos instance (repos) in the Git plugin, locked by a
     internal lock (all methods are synchronized).
"""

import fnmatch
import os
import shutil

from supybot import callbacks
from supybot import ircmsgs
from supybot import log
from supybot import schedule
from supybot import world
from supybot.commands import commalist
from supybot.commands import optional
from supybot.commands import threading
from supybot.commands import time
from supybot.commands import wrap
from supybot.utils.str import pluralize

import config

try:
    import git
except ImportError:
    raise Exception("GitPython is not installed.")
if not git.__version__.startswith('0.'):
    raise Exception("Unsupported GitPython version.")
if not int(git.__version__[2]) == 3:
    raise Exception("Unsupported GitPython version: " + git.__version__[2])
from git import GitCommandError


class GitPluginException(Exception):
    ''' Common base class for exceptions in this plugin. '''
    pass


def _plural(count, singular, plural=None):
    ''' Return singular/plural form of singular arg depending on count. '''
    if abs(count) <= 1:
        return singular
    return plural if plural else pluralize(singular)


def _get_commits(repo, first, last):
    ''' Return list of commits in repo from first to last, inclusive.'''
    rev = "%s..%s" % (first, last)
    # Workaround for GitPython bug:
    # https://github.com/gitpython-developers/GitPython/issues/61
    repo.odb.update_cache()
    return repo.iter_commits(rev)


def _format_message(repository, commit, branch='unknown'):
    """
    Generate an formatted message for IRC from the given commit, using
    the format specified in the config. Returns a list of strings.
    """
    MODE_NORMAL = 0
    MODE_SUBST = 1
    MODE_COLOR = 2
    subst = {
        'a': commit.author.name,
        'b': branch,
        'c': commit.hexsha[0:7],
        'C': commit.hexsha,
        'e': commit.author.email,
        'm': commit.message.split('\n')[0],
        'n': repository.name,
        'S': ' ',
        'u': repository.options.url,
        'r': '\x0f',
        '!': '\x02',
        '%': '%',
    }
    result = []
    lines = repository.options.commit_msg.split('\n')
    for line in lines:
        mode = MODE_NORMAL
        outline = ''
        for c in line:
            if mode == MODE_SUBST:
                if c in subst.keys():
                    outline += subst[c]
                    mode = MODE_NORMAL
                elif c == '(':
                    color = ''
                    mode = MODE_COLOR
                else:
                    outline += c
                    mode = MODE_NORMAL
            elif mode == MODE_COLOR:
                if c == ')':
                    outline += '\x03' + color
                    mode = MODE_NORMAL
                else:
                    color += c
            elif c == '%':
                mode = MODE_SUBST
            else:
                outline += c
        result.append(outline.encode('utf-8'))
    return result


def _get_branches(option_val, repo):
    ''' Return list of branches in repo matching users's option_val. '''
    log_ = log.getPluginLogger('git.get_branches')
    opt_branches = [b.strip() for b in option_val.split()]
    repo.remote().update()
    repo_branches = \
        [r.name.split('/')[1] for r in repo.remote().refs if r.is_detached]
    branches = []
    for opt in opt_branches:
        matched = fnmatch.filter(repo_branches, opt)
        if not matched:
            log_.warning("No branch in repository matches " + opt)
        else:
            branches.extend(matched)
    if not branches:
        log_.error("No branch in repository matches: " + option_val)
    return branches


class _Repository(object):
    """
    Represents a git repository being monitored. The repository is a
    critical zone accessed both by main thread and the GitFetcher,
    guarded by the lock attribute.
    """

    class Options(object):
        ''' Simple container for option values. '''
        # pylint: disable=R0902

        def __init__(self, reponame):

            def get_value(key):
                ''' Read a registry value. '''
                return config.repo_option(reponame, key).value

            self.repo_dir = config.global_option('repoDir').value
            self.name = reponame
            self.url = get_value('url')
            self.channels = get_value('channels')
            self.branches = get_value('branches')
            self.commit_msg = get_value('commitMessage1')
            if get_value('commitMessage2'):
                self.commit_msg += "\n" + get_value('commitMessage2')
            self.group_header = get_value('groupHeader')
            self.enable_snarf = get_value('enableSnarf')
            self.timeout = get_value('fetchTimeout')
            self.repo = config.global_option('repos').get(reponame)

    def __init__(self, reponame):
        """
        Initialize a repository with the given name. If cloning_done_cb
        is set, force a git clone. Data is read from supybot configuration.
        """
        self.log = log.getPluginLogger('git.repository')
        self.options = self.Options(reponame)
        self.commit_by_branch = {}
        self.lock = threading.Lock()
        self.repo = None
        self.path = os.path.join(self.options.repo_dir, self.options.name)
        if world.testing:
            self._clone()
            self.init()

    name = property(lambda self: self.options.name)

    timeout = property(lambda self: self.options.timeout)

    branches = property(lambda self: self.commit_by_branch.keys())

    @staticmethod
    def create(reponame, cloning_done_cb = lambda x: True, opts = None):
        '''
        Create a new repository, clone and invoke cloning_done_cb on main
        thread. callback is called with a _Repository or an error msg.
        opts need to contain at least name, url and channels.
        '''
        if not opts:
            opts = {}
        for key, value in opts.iteritems():
            config.repo_option(reponame, key).setValue(value)
        r = _Repository(reponame)
        try:
            r._clone()                             # pylint: disable=W0212
            r.init()
            todo = lambda: cloning_done_cb(r)
        except (GitCommandError, git.exc.NoSuchPathError) as e:
            todo = lambda: cloning_done_cb(str(e))
        _Scheduler.run_callback(todo, 'clonecallback')

    def _clone(self):
        "If the repository doesn't exist on disk, clone it."
        # pylint: disable=E0602
        if not os.path.exists(self.options.repo_dir):
            os.makedirs(self.options.repo_dir)
        if os.path.exists(self.path):
            shutil.rmtree(self.path)
        git.Git('.').clone(self.options.url, self.path, no_checkout=True)

    def init(self):
        ''' Lazy init, invoked after a clone exists. '''
        self.repo = git.Repo(self.path)
        self.commit_by_branch = {}
        for branch in _get_branches(self.options.branches, self.repo):
            try:
                if str(self.repo.active_branch) == branch:
                    self.repo.remote().pull(branch)
                else:
                    self.repo.remote().fetch(branch + ':' + branch)
                self.commit_by_branch[branch] = self.repo.commit(branch)
            except GitCommandError as e:
                self.log.error("Cannot checkout repo branch: " + branch)
                raise e
        return self

    def fetch(self, timeout=300):
        "Contact git repository and update branches appropriately."
        self.repo.remote().update()
        for branch in self.branches:
            try:
                timer = threading.Timer(timeout, lambda: [][5])
                timer.start()
                if str(self.repo.active_branch) == branch:
                    self.repo.remote().pull(branch)
                else:
                    self.repo.remote().fetch(branch + ':' + branch)
                timer.cancel()
            except IndexError:
                self.log.error('Timeout in fetch() for %s at %s' %
                                   (branch, self.name))
            except OSError as e:
                self.log.error("Problem accessing local repo: " +
                               str(e))

    def get_commit(self, sha):
        "Fetch the commit with the given SHA, throws BadObject."
        # pylint: disable=E0602
        return self.repo.commit(sha)

    def get_new_commits(self):
        '''
        Return dict of commits by branch which are more recent then those
        in self.commit_by_branch
        '''
        new_commits_by_branch = {}
        for branch in self.commit_by_branch:
            result = _get_commits(self.repo,
                                  self.commit_by_branch[branch],
                                  branch)
            results = list(result)
            new_commits_by_branch[branch] = results
            self.log.debug("Poll: branch: %s last commit: %s, %d commits" %
                           (branch, str(self.commit_by_branch[branch])[:7],
                                        len(results)))
        return new_commits_by_branch

    def get_recent_commits(self, branch, count):
        ''' Return count top commits for a branch in a repo. '''
        return list(self.repo.iter_commits(branch))[:count]


class _Repos(object):
    '''
    Synchronized access to the list of _Repository and related
    conf settings.
    '''

    def __init__(self):
        self._lock = threading.Lock()
        self._list = []
        for repo in config.global_option('repolist').value:
            self.append(_Repository(repo).init())

    def set(self, repositories):
        ''' Update the repository list. '''
        with self._lock:
            self._list = repositories
            repolist = [r.name for r in repositories]
            config.global_option('repolist').setValue(repolist)

    def append(self, repository):
        ''' Add new repository to shared list. '''
        with self._lock:
            self._list.append(repository)
            repolist = [r.name for r in self._list]
            config.global_option('repolist').setValue(repolist)

    def remove(self, repository):
        ''' Remove repository from list. '''
        with self._lock:
            self._list.remove(repository)
            repolist = [r.name for r in self._list]
            config.global_option('repolist').setValue(repolist)
            config.unregister_repo(repository.name)

    def get(self):
        ''' Return copy of the repository list. '''
        with self._lock:
            return list(self._list)


class _GitFetcher(threading.Thread):
    """
    Thread replicating remote data to local repos roughly using git pull and
    git fetch. When done schedules a poll_all_repos call and exits.
    """

    def __init__(self, repos, fetch_done_cb):

        self.log = log.getPluginLogger('git.fetcher')
        threading.Thread.__init__(self)
        self._shutdown = False
        self._repos = repos
        self._callback = fetch_done_cb

    def stop(self):
        """
        Shut down the thread as soon as possible. May take some time if
        inside a long-running fetch operation.
        """
        self._shutdown = True

    def run(self):
        start = time.time()
        for repository in self._repos.get():
            if self._shutdown:
                break
            try:
                with repository.lock:
                    if not repository.repo:
                        raise GitPluginException(repository.name +
                                                 ": not cloned")
                    repository.fetch(repository.timeout)
            except GitCommandError as e:
                self.log.error("Error in git command: " + str(e),
                                   exc_info=True)
            except GitPluginException as e:
                    self.log.warning(str(e))
        _Scheduler.run_callback(self._callback, 'fetch_callback')
        self.log.debug("Exiting fetcher thread, elapsed: " +
                       str(time.time() - start))


class _DisplayCtx:
    ''' Simple container for displaying commits stuff. '''
    SNARF = 'snarf'
    REPOLOG = 'repolog'
    COMMITS = 'commits'

    def __init__(self, irc, channel, repository, kind=None):
        self.irc = irc
        self.channel = channel
        self.repo = repository
        self.kind = kind if kind else self.COMMITS

    @property
    def use_group_header(self):
        ''' Return True if the group header should be applied. '''
        return self.repo.options.group_header and self.kind != self.REPOLOG


class _Scheduler(object):
    '''
    Handles scheduling of fetch and poll tasks.

    Polling happens in three steps:
     -  reset()  kills all active jobs  and schedules
        start_fetch to be invoked periodically.
     -  start_fetch() fires off the one-shot GitFetcher
        thread which handles the long-running git replication.
     -  When done, the GitFetcher thread invokes Scheduler.run_callback.
        This invokes poll_all_repos in main thread but this is quick,
        (almost) no remote IO is needed.
    '''

    def __init__(self, git_):
        self.log = log.getPluginLogger('git.conf')
        self._git = git_
        self.fetcher = None
        self.reset()

    fetching_alive = \
        property(lambda self: self.fetcher and self.fetcher.is_alive())

    def reset(self, die=False):
        '''
        Revoke scheduled events, start a new fetch right now unless
        die or testing.
        '''
        for ev in ['repofetch', 'repopoll', 'repocallback']:
            try:
                schedule.removeEvent(ev)
            except KeyError:
                pass
        if die or world.testing:
            return
        pollPeriod = config.global_option('pollPeriod').value
        if not pollPeriod:
            self.log.debug("Scheduling: ignoring reset with pollPeriod 0")
            return
        schedule.addPeriodicEvent(lambda: _Scheduler.start_fetch(self),
                                  pollPeriod,
                                 'repofetch',
                                  not self.fetching_alive)
        self.log.debug("Restarted polling")

    def stop(self):
        '''
        Stop  the gitFetcher. Never allow an exception to propagate since
        this is called in die()
        '''
        # pylint: disable=W0703
        if self.fetching_alive:
            try:
                self.fetcher.stop()
                self.fetcher.join()    # This might take time, but it's safest.
            except Exception, e:
                self.log.error('Stopping fetcher: %s' % str(e),
                               exc_info=True)
        self.reset(die = True)

    def start_fetch(self):
        ''' Start next GitFetcher run. '''
        if not config.global_option('pollPeriod').value:
            return
        if self.fetching_alive:
            self.log.error("Fetcher running when about to start!")
            self.fetcher.stop()
            self.fetcher.join()
            self.log.info("Stopped fetcher")
        self.fetcher = _GitFetcher(self._git.repos,
                                   lambda: Git.poll_all_repos(self._git))
        self.fetcher.start()

    @staticmethod
    def run_callback(callback, id_):
        ''' Run the callback 'now' on main thread. '''
        try:
            schedule.removeEvent(id_)
        except KeyError:
            pass
        schedule.addEvent(callback, time.time(), id_)


class Git(callbacks.PluginRegexp):
    "Please see the README file to configure and use this plugin."
    # pylint: disable=R0904

    threaded = True
    unaddressedRegexps = ['_snarf']

    def __init__(self, irc):
        # pylint: disable=W0233,W0231
        callbacks.PluginRegexp.__init__(self, irc)
        self.repos = _Repos()
        self.scheduler = _Scheduler(self)
        if hasattr(irc, 'reply'):
            n = len(self.repos.get())
            msg = 'Git reinitialized with ' + str(n) + ' '
            msg += _plural(n, 'repository') + '.'
            irc.reply(msg)

    def _display_some_commits(self, ctx, commits, branch):
        "Display a nicely-formatted list of commits for an author/branch."
        for commit in commits:
            lines = _format_message(ctx.repo, commit, branch)
            for line in lines:
                msg = ircmsgs.privmsg(ctx.channel, line)
                ctx.irc.queueMsg(msg)

    def _get_limited_commits(self, ctx, commits_by_branch):
        "Return the topmost commits which are OK to display."
        top_commits = []
        for key in commits_by_branch.keys():
            top_commits.extend(commits_by_branch[key])
        top_commits = sorted(top_commits, key = lambda c: c.committed_date)
        commits_at_once = self.registryValue('maxCommitsAtOnce')
        if len(top_commits) > commits_at_once:
            ctx.irc.queueMsg(ircmsgs.privmsg(ctx.channel,
                             "Showing latest %d of %d commits to %s..." % (
                             commits_at_once,
                             len(top_commits),
                             ctx.repo.name,
                             )))
        top_commits = top_commits[-commits_at_once:]
        return top_commits

    def _display_commits(self, ctx, commits_by_branch):
        "Display a nicely-formatted list of commits in a channel."

        if not commits_by_branch:
            return
        top_commits = self._get_limited_commits(ctx, commits_by_branch)
        for branch, all_commits in commits_by_branch.iteritems():
            for a in set([c.author.name for c in all_commits]):
                commits = [c for c in all_commits
                               if c.author.name == a and c in top_commits]
                if not ctx.use_group_header:
                    self._display_some_commits(ctx, commits, branch)
                    continue
                if ctx.kind == _DisplayCtx.SNARF:
                    line = "Talking about %s?" % commits[0].hexsha[0:7]
                else:
                    name = ctx.repo.options.name
                    line = "%s pushed %d commit(s) to %s at %s" % (
                        a, len(commits), branch, name)
                msg = ircmsgs.privmsg(ctx.channel, line)
                ctx.irc.queueMsg(msg)
                self._display_some_commits(ctx, commits, branch)

    def _poll_repository(self, repository, targets):
        ''' Perform poll of a repo, display changes. '''
        try:
            with repository.lock:
                new_commits_by_branch = repository.get_new_commits()
                for irc, channel in targets:
                    ctx = _DisplayCtx(irc, channel, repository)
                    self._display_commits(ctx, new_commits_by_branch)
                for branch in new_commits_by_branch:
                    repository.commit_by_branch[branch] = \
                       repository.get_commit(branch)
        except GitCommandError as e:
            self.log.error('Exception in _poll repository %s: %s' %
                (repository.options.name, str(e)))

    def _parse_repo(self, irc, msg, repo, channel):
        """ Parse first parameter as a repo, return repository or None. """
        matches = filter(lambda r: r.options.name == repo,
                         self.repos.get())
        if not matches:
            irc.reply('No repository named %s, showing available:'
                      % repo)
            self.repolist(irc, msg, [])
            return None
        # Enforce a modest privacy measure... don't let people probe the
        # repository outside the designated channel.
        repository = matches[0]
        if channel not in repository.options.channels:
            irc.reply('Sorry, not allowed in this channel.')
            return None
        return repository

    def _snarf(self, irc, msg, match):
        r"""\b(?P<sha>[0-9a-f]{6,40})\b"""
        sha = match.group('sha')
        channel = msg.args[0]
        repositories = [r for r in self.repos.get()
                            if channel in r.options.channels]
        for repository in repositories:
            if not repository.options.enable_snarf:
                continue
            try:
                commit = repository.get_commit(sha)
            except git.exc.BadObject:
                continue
            ctx = _DisplayCtx(irc, channel, repository, _DisplayCtx.SNARF)
            self._display_commits(ctx, {'unknown': [commit]})
            break

    def poll_all_repos(self):
        ''' Look for and handle new commits in local copy of repo. '''
        start = time.time()
        for repository in self.repos.get():
            # Find the IRC/channel pairs to notify
            targets = []
            for irc in world.ircs:
                for channel in repository.options.channels:
                    if channel in irc.state.channels:
                        targets.append((irc, channel))
            if not targets:
                self.log.info("Skipping %s: not in configured channel(s)." %
                              repository.name)
                continue
            try:
                self._poll_repository(repository, targets)
            except Exception as e:                      # pylint: disable=W0703
                self.log.error('Exception in _poll():' + str(e),
                                exc_info=True)
        self.log.debug("Exiting poll_all_repos, elapsed: " +
                       str(time.time() - start))

    def die(self):
        ''' Stop all threads.  '''
        self.scheduler.stop()
        callbacks.PluginRegexp.die(self)

    def repolog(self, irc, msg, args, channel, repo, branch, count):
        """ repo [branch [count]]

        Display the last commits on the named repository. branch defaults
        to 'master', count defaults to 1 if unspecified.
        """
        repository = self._parse_repo(irc, msg, repo, channel)
        if not repository:
            return
        if not branch in repository.branches:
            irc.reply('No such branch being watched: ' + branch)
            irc.reply('Available branches: ' +
                          ', '.join(repository.branches))
            return
        try:
            branch_head = repository.get_commit(branch)
        except GitCommandError:
            self.log.info("Cant get branch commit", exc_info=True)
            irc.reply("Internal error retrieving repolog data")
            return
        commits = repository.get_recent_commits(branch_head, count)[::-1]
        ctx = _DisplayCtx(irc, channel, repository, _DisplayCtx.REPOLOG)
        self._display_commits(ctx, {branch: commits})

    repolog = wrap(repolog, ['channel',
                             'somethingWithoutSpaces',
                             optional('somethingWithoutSpaces', 'master'),
                             optional('positiveInt', 1)])

    def repolist(self, irc, msg, args, channel):
        """(takes no arguments)

        Display the names of known repositories configured for this channel.
        """
        repositories = filter(lambda r: channel in r.options.channels,
                              self.repos.get())
        if not repositories:
            irc.reply('No repositories configured for this channel.')
            return
        fmt = '\x02%(name)s\x02  %(url)s %(cnt)d %(branch)s'
        for r in repositories:
            irc.reply(fmt % {
                'name': r.name,
                'url': r.options.url,
                'cnt': len(r.branches),
                'branch': _plural(len(r.branches), 'branch')
            })

    repolist = wrap(repolist, ['channel'])

    def repostat(self, irc, msg, args, channel, repo):
        """ <repository name>
        Display the watched branches for a given repository.
        """
        repository = self._parse_repo(irc, msg, repo, channel)
        if not repository:
            return
        irc.reply('Watched branches: ' + ', '.join(repository.branches))

    repostat = wrap(repostat, ['channel', 'somethingWithoutSpaces'])

    def repoadd(self, irc, msg, args, channel, reponame, url, channels):
        """ <repository name> <url> <channel[,channel...]>

        Add a new repository with name, url and a comma-separated list
        of channels which should be connected to this repo.
        """

        def cloning_done_cb(result):
            ''' Callback invoked after cloning si done. '''
            if isinstance(result, _Repository):
                self.repos.append(result)
                irc.reply("Repository created and cloned")
            else:
                self.log.info("Cannot clone: " + str(result))
                irc.reply("Error: Cannot clone repo: " + str(result))

        if reponame in config.global_option('repolist').value:
            irc.reply('Error: repo exists')
            return
        opts = {'url': url, 'name': reponame, 'channels': channels}
        t = threading.Thread(target= _Repository.create,
                             args=(reponame, cloning_done_cb, opts))
        t.start()

    repoadd = wrap(repoadd, ['owner',
                             'channel',
                             'somethingWithoutSpaces',
                             'somethingWithoutSpaces',
                             commalist('validChannel')])

    def repokill(self, irc, msg, args, channel, reponame):
        """ <repository name>

        Removes an existing repository given it's name.
        """
        found_repos = [r for r in self.repos.get() if r.name == reponame]
        if not found_repos:
            irc.reply('Error: repo does not exist')
            return
        self.repos.remove(found_repos[0])
        shutil.rmtree(found_repos[0].path)
        irc.reply('Repository deleted')

    repokill = wrap(repokill,
                    ['owner', 'channel', 'somethingWithoutSpaces'])

Class = Git


# vim:set shiftwidth=4 tabstop=4 expandtab textwidth=79:
