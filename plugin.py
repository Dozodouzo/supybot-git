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
with the related inital git clone operation. ATM, this is in main thread.

The critical sections are:
   - The _Repository instances, locked with an instance attribute lock.
   - The Repos instance (repos) in the Git plugin, locked by a
     internal lock (all methods are synchronized).
"""

from supybot.commands import optional
from supybot.commands import commalist
from supybot.commands import threading
from supybot.commands import time
from supybot.commands import wrap
from supybot.utils.str import pluralize

import supybot.conf as conf
import supybot.ircmsgs as ircmsgs
import supybot.callbacks as callbacks
import supybot.schedule as schedule
import supybot.log as log
import supybot.registry as registry
import supybot.world as world

import fnmatch
import os
import shutil
import threading
import time

try:
    import git
except ImportError:
    raise Exception("GitPython is not installed.")
if not git.__version__.startswith('0.'):
    raise Exception("Unsupported GitPython version.")
if not int(git.__version__[2]) == 3:
    raise Exception("Unsupported GitPython version: " + git.__version__[2])
from git import GitCommandError


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


def _format_link(repository, commit):
    "Return a link to view a given commit, based on config setting."
    result = ''
    escaped = False
    for c in repository.options.commit_link:
        if escaped:
            if c == 'c':
                result += commit.hexsha[0:7]
            elif c == 'C':
                result += commit.hexsha
            else:
                result += c
            escaped = False
        elif c == '%':
            escaped = True
        else:
            result += c
    return result


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
        'l': _format_link(repository, commit),
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

_URL_TEXT = "The URL to the git repository, which may be a path on" \
            " disk, or a URL to a remote repository."""

_NAME_TXT = "This is the nickname you use in all commands that interact " \
            " that interact with the repository"""

_SNARF_TXT = "Eavesdrop and send commit info if a commit id is found in " \
             " IRC chat"""

_CHANNELS_TXT = """A space-separated list of channels where
 notifications of new commits will appear.  If you provide more than one
 channel, all channels will receive commit messages.  This is also a weak
 privacy measure; people on other channels will not be able to request
 information about the repository. All interaction with the repository is
 limited to these channels."""

_BRANCHES_TXT = """Space-separated list fo branches to follow for
 this repository. Accepts wildcards, * means all branches, release*
 all branches beginnning with releas.e"""

_LINK_TXT = """ A format string describing how to link to a
 particular commit. These links may appear in commit notifications from the
 plugin.  Two format specifiers are supported: %c (7-digit SHA) and %C (full
 40-digit SHA)."""

_MESSAGE_TXT = """A format string describing how to describe
 commits in the channel.  See  https://github.com/leamas/supybot-git for
 details."""

_GROUP_HDR_TXT = """ A boolean setting. If true, the commits for
 each author is preceded by a single line like 'John le Carre committed
 5 commits to our-game". A line like "Talking about fa1afe1?" is displayed
 before presenting data for a commit id found in the irc conversation."""

_TIMEOUT_TXT = """Max time for fetch operations (seconds). A value of 0
disables polling of this repo completely"""


def _register_repo(repo_group):
    ''' Register a repository. '''
    conf.registerGlobalValue(repo_group, 'name',
                             registry.String('', _NAME_TXT))
    conf.registerGlobalValue(repo_group, 'url',
                             registry.String('', _URL_TEXT))
    conf.registerGlobalValue(repo_group, 'channels',
            registry.SpaceSeparatedListOfStrings('', _CHANNELS_TXT))
    conf.registerGlobalValue(repo_group, 'branches',
                             registry.String('*', _BRANCHES_TXT))
    conf.registerGlobalValue(repo_group, 'commitLink',
                             registry.String('', _LINK_TXT))
    conf.registerGlobalValue(repo_group, 'commitMessage',
                             registry.String('[%n|%b|%a] %m', _MESSAGE_TXT))
    conf.registerGlobalValue(repo_group, 'enableSnarf',
                             registry.Boolean(True, _SNARF_TXT))
    conf.registerGlobalValue(repo_group, 'groupHeader',
                             registry.Boolean(True, _GROUP_HDR_TXT))
    conf.registerGlobalValue(repo_group, 'fetchTimeout',
                             registry.Integer(300, _TIMEOUT_TXT))


def _register_repos(plugin, plugin_group):
    ''' Register the dynamically created repo definitins. '''

    repos = conf.registerGroup(plugin_group, 'repos')
    conf.registerGlobalValue(plugin_group, 'repolist',
        registry.String('', 'List of configured repos'))
    repo_list = plugin.registryValue('repolist').split()
    for repo in repo_list:
        repo_group = conf.registerGroup(repos, repo)
        _register_repo(repo_group)


def get_branches(option_val, repo, log_):
    ''' Return list of branches in repo matching users's option_val. '''
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


class GitPluginException(Exception):
    ''' Common base class for exceptions in this plugin. '''
    pass


def on_timeout():
    ''' Handler for Timer events. '''
    raise GitPluginException('timeout')


class _RepoOptions(object):
    ''' Simple container for option values. '''
    # pylint: disable=R0902

    def __init__(self, plugin, repo_name):

        def get_value(key, default = None):
            ''' Read a registry value, return default on missing. '''
            try:
                key = 'repos.' + repo_name + '.' + key
                return plugin.registryValue(key)
            except registry.NonExistentRegistryEntry as e:
                if default:
                    return default
                else:
                    raise e

        self.repo_dir = plugin.registryValue('repoDir')
        self.name = repo_name
        self.url = get_value('url')
        self.channels = get_value('channels')
        self.branches = get_value('branches', 'master')
        self.commit_msg = get_value('commitMessage', '[%s|%b|%a] %m')
        self.commit_link = get_value('commitLink', '')
        self.group_header = get_value('group header', True)
        self.enable_snarf = get_value('enableSnarf', True)
        self.timeout = get_value('fetchTimeout', 300)


class _Repository(object):
    """
    Represents a git repository being monitored. The repository is critical
    zone accessed both by main thread and the GitWatcher, guarded by
    the lock attribute.
    """

    def __init__(self, options, log_):
        """
        Initialize with a repository with the given name and dict of options
        from the config section.
        """
        self.log = log_
        self.options = options
        self.commit_by_branch = {}
        self.lock = threading.Lock()
        self.repo = None
        if not os.path.exists(options.repo_dir):
            os.makedirs(options.repo_dir)
        self.path = os.path.join(options.repo_dir, options.name)

        if world.testing:
            self.clone()

    name = property(lambda self: self.options.name)

    timeout = property(lambda self: self.options.timeout)

    branches = property(lambda self: self.commit_by_branch.keys())

    def clone(self):
        "If the repository doesn't exist on disk, clone it."

        # pylint: disable=E0602
        if not os.path.exists(self.path):
            git.Git('.').clone(self.options.url, self.path, no_checkout=True)
        self.repo = git.Repo(self.path)
        self.commit_by_branch = {}
        for branch in get_branches(
                                self.options.branches, self.repo, self.log):
            try:
                if str(self.repo.active_branch) == branch:
                    self.repo.remote().pull(branch)
                else:
                    self.repo.remote().fetch(branch + ':' + branch)
                self.commit_by_branch[branch] = self.repo.commit(branch)
            except GitCommandError:
                self.log.error("Cannot checkout repo branch: " + branch)

    def fetch(self, timeout=300):
        "Contact git repository and update branches appropriately."
        self.repo.remote().update()
        for branch in self.branches:
            try:
                timer = threading.Timer(timeout, on_timeout)
                timer.start()
                if str(self.repo.active_branch) == branch:
                    self.repo.remote().pull(branch)
                else:
                    self.repo.remote().fetch(branch + ':' + branch)
                timer.cancel()
            except GitPluginException:
                self.log.error('Timeout in fetch() for %s at %s' %
                                   (branch, self.name))

    def get_commit(self, sha):
        "Fetch the commit with the given SHA, throws GitCommandError."
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

    def __init__(self, plugin):
        self._lock = threading.Lock()
        self._plugin = plugin
        self._list = []
        repos = conf.supybot.plugins.get(plugin.name()).get('repos')
        for repo in repos._children.keys():      # pylint: disable=W0212
            options = _RepoOptions(plugin, repo)
            self.append(_Repository(options, plugin.log))

    def set(self, repositories):
        ''' Update the repository list. '''
        with self._lock:
            self._list = repositories
            repolist = [r.name for r in repositories]
            self._plugin.setRegistryValue('repolist', ' '.join(repolist))

    def append(self, repository):
        ''' Add new repository to shared list. '''
        with self._lock:
            self._list.append(repository)
            repolist = [r.name for r in self._list]
            self._plugin.setRegistryValue('repolist', ' '.join(repolist))

    def get(self):
        ''' Return copy of the repository list. '''
        with self._lock:
            return list(self._list)


class _GitFetcher(threading.Thread):
    "A thread object to perform long-running Git operations."

    # I don't know of any way to shut down a thread except to have it
    # check a variable very frequently.
    SHUTDOWN_CHECK_PERIOD = 0.1     # Seconds

    def __init__(self, plugin, *args, **kwargs):
        """
        Takes a list of repositories and a period (in seconds) to poll them.
        As long as it is running, the repositories will be kept up to date
        every period seconds (with a git fetch).
        """
        super(_GitFetcher, self).__init__(*args, **kwargs)
        self.log = plugin.log
        self.period = plugin.registryValue('pollPeriod')
        self.period *= 1.1      # Hacky attempt to avoid resonance
        self.shutdown = False
        self.plugin = plugin

    def stop(self):
        """
        Shut down the thread as soon as possible. May take some time if
        inside a long-running fetch operation.
        """
        self.shutdown = True

    def run(self):
        "The main thread method."
        # Initially wait for half the period to stagger this thread and
        # the main thread and avoid lock contention.
        end_time = time.time() + self.period / 2
        while not self.shutdown:
            for repository in self.plugin.repos.get():
                if self.shutdown:
                    break
                if repository.lock.acquire(False):
                    try:
                        if not repository.repo:
                            repository.clone()
                        repository.fetch(repository.timeout)
                    except GitCommandError as e:
                        self.log.error("Error in git command: " + str(e),
                                       exc_info=True)
                    finally:
                        repository.lock.release()
                else:
                    self.log.info(
                        'Postponing repository fetch: %s: Locked.' %
                        repository.name)
            # Wait for the next periodic check
            while not self.shutdown and time.time() < end_time:
                time.sleep(_GitFetcher.SHUTDOWN_CHECK_PERIOD)
            end_time = time.time() + self.period


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


class Git(callbacks.PluginRegexp):
    "Please see the README file to configure and use this plugin."
    # pylint: disable=R0904

    threaded = True
    unaddressedRegexps = ['_snarf']

    def __init__(self, irc):
        # pylint: disable=W0233,W0231
        self.__parent = super(Git, self)
        self.__parent.__init__(irc)
        self.fetcher = None
        plugin_group = conf.supybot.plugins.get(self.name())
        _register_repos(self, plugin_group)
        self._stop_polling()
        try:
            self.repos = _Repos(self)
        except registry.NonExistentRegistryEntry as e:
            self.log.error(str(e), exc_info=True)
            if 'reply' in dir(irc):
                irc.reply('Error: %s' % str(e))
        self._schedule_next_event()

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

    def _schedule_next_event(self):
        ''' Schedule next run for gitFetcher. '''
        period = self.registryValue('pollPeriod')
        if period > 0:
            if not self.fetcher or not self.fetcher.isAlive():
                self.fetcher = _GitFetcher(self)
                self.fetcher.start()
            schedule.addEvent(self._poll, time.time() + period,
                              name=self.name())
        else:
            self._stop_polling()

    def _poll_repository(self, repository, targets):
        ''' Perform poll of a repo, display changes. '''
        # Manual non-blocking lock calls here to avoid potentially long
        # waits (if it fails, hope for better luck in the next _poll).
        if repository.lock.acquire(False):
            try:
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
            finally:
                repository.lock.release()
        else:
            log.info('Postponing repository read: %s: Locked.' %
                repository.name)

    def _poll(self):
        ''' Look for and handle new commits in local copy of repo. '''
        # Note that polling happens in two steps:
        #
        # 1. The _GitFetcher class, running its own poll loop, fetches
        #    repositories to keep the local copies up to date.
        # 2. This _poll occurs, and looks for new commits in those local
        #    copies.  (Therefore this function should be quick. If it is
        #    slow, it may block the entire bot.)
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
            except Exception, e:                        # pylint: disable=W0703
                self.log.error('Exception in _poll():' + str(e),
                                exc_info=True)
        self._schedule_next_event()

    def _stop_polling(self):
        '''
        Stop  the gitFetcher. Never allow an exception to propagate since
        this is called in die()
        '''
        # pylint: disable=W0703
        if self.fetcher:
            try:
                self.fetcher.stop()
                self.fetcher.join()    # This might take time, but it's safest.
            except Exception, e:
                self.log.error('Stopping fetcher: %s' % str(e),
                               exc_info=True)
            self.fetcher = None
        try:
            schedule.removeEvent(self.name())
        except KeyError:
            pass
        except Exception, e:
            self.log.error('Stopping scheduled task: %s' % str(e),
                            exc_info=True)

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

    def die(self):
        ''' Stop all threads.  '''
        self._stop_polling()
        self.__parent.die()

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

    def rehash(self, irc, msg, args):
        """(takes no arguments)

        Reload the settings and restart any period polling.
        """
        self._stop_polling()
        try:
            self.repos = _Repos(self)
        except registry.NonExistentRegistryEntry as e:
            irc.reply('Error: %s' % str(e))
        self._schedule_next_event()
        n = len(self.repos.get())
        irc.reply('Git reinitialized with %d %s.' %
                      (n, _plural(n, 'repository')))

    rehash = wrap(rehash, [])

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

    def branches(self, irc, msg, args, channel, repo):
        """ <repository name>
        Display the watched branches for a given repository.
        """
        repository = self._parse_repo(irc, msg, repo, channel)
        if not repository:
            return
        irc.reply('Watched branches: ' + ', '.join(repository.branches))

    branches = wrap(branches, ['channel', 'somethingWithoutSpaces'])

    def repoadd(self, irc, msg, args, channel, repo, url, channels):
        """ <repository name> <url> <channel[,channel...]>

        Add a new repository with name, url and a comma-separated list
        of channels which should be connected to this repo.
        """
        repolist = self.registryValue('repolist').split()
        if repo in repolist:
            irc.reply('Error: repo exists')
            return
        repos = conf.supybot.plugins.get(self.name()).get('repos')
        _register_repo(conf.registerGroup(repos, repo))
        key = 'repos.' + repo + '.'
        self.setRegistryValue(key + 'url', url)
        self.setRegistryValue(key + 'name', repo)
        self.setRegistryValue(key + 'channels', channels)
        options = _RepoOptions(self, repo)
        repository = _Repository(options, self.log)
        if os.path.exists(repository.path):
            shutil.rmtree(repository.path)
        try:
            repository.clone()
        except GitCommandError as e:
            self.log.info("Cannot clone: " + str(e), exc_info=True)
            irc.reply("Error: Cannot clone repo (%s)." % str(e))
            return
        self.repos.append(repository)
        irc.reply("Repository created and cloned")

    repoadd = wrap(repoadd, ['owner',
                             'channel',
                             'somethingWithoutSpaces',
                             'somethingWithoutSpaces',
                             commalist('validChannel')])

    def repokill(self, irc, msg, args, channel, reponame):
        """ <repository name>

        Removes an existing repository given it's name.
        """
        all_repos = self.repos.get()
        found_repos = [r for r in all_repos if r.name == reponame]
        if not found_repos:
            irc.reply('Error: repo does not exist')
            return
        all_repos.remove(found_repos[0])
        self.repos.set(all_repos)
        repos_group = conf.supybot.plugins.get(self.name()).get('repos')
        try:
            repos_group.unregister(reponame)
        except registry.NonExistentRegistryEntry:
            pass
        irc.reply('Repo deleted')

    repokill = wrap(repokill,
                    ['owner', 'channel', 'somethingWithoutSpaces'])

Class = Git


# vim:set shiftwidth=4 tabstop=4 expandtab textwidth=79:
