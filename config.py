###
# Copyright (c) 2009, Mike Mueller
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#   * Redistributions of source code must retain the above copyright notice,
#     this list of conditions, and the following disclaimer.
#   * Redistributions in binary form must reproduce the above copyright notice,
#     this list of conditions, and the following disclaimer in the
#     documentation and/or other materials provided with the distribution.
#   * Neither the name of the author of this software nor the name of
#     contributors to this software may be used to endorse or promote products
#     derived from this software without specific prior written consent.
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

''' Overall configuration reflecting supybot.git.* config variables. '''

# pylint: disable=W0612

from supybot import conf
from supybot import registry

_URL_TEXT = "The URL to the git repository, which may be a path on" \
            " disk, or an URL to a remote repository."""

_SNARF_TXT = "Eavesdrop and send commit info if a commit id is found in" \
             " IRC chat"""

_CHANNELS_TXT = """A space-separated list of channels where
 notifications of new commits will appear.  If you provide more than one
 channel, all channels will receive commit messages. This is also a weak
 privacy measure; people on other channels will not be able to request
 information about the repository. All interaction with the repository is
 limited to these channels."""

_BRANCHES_TXT = """Space-separated list of branches to follow for
 this repository. Accepts wildcards, * means all branches, release*
 all branches beginnning with release."""

_MESSAGE1_TXT = """First line of message describing a commit in e. g., log
 messages. Constructed from printf-style substitutions.  See
 https://github.com/leamas/supybot-git for details."""

_MESSAGE2_TXT = """Second line of message describing a commit in e. g., log
 messages. Often used for a view link. Constructed from printf-style
 substitutions, see https://github.com/leamas/supybot-git for details."""

_SNARFMSG1_TXT = """First line of message describing a commit in a snarf
 message. Constructed from printf-style substitutions.  See
 https://github.com/leamas/supybot-git for details."""

_SNARFMSG2_TXT = """Second line of message describing a commit in
 a  snarf  message. Often used for a view link. Constructed from printf-style
 substitutions, see https://github.com/leamas/supybot-git for details."""

_GROUP_HDR_TXT = """A boolean setting. If true, the commits for
 each author is preceded by a single line like 'John le Carre committed
 5 commits to our-game". A line like "Talking about fa1afe1?" is displayed
 before presenting data for a commit id found in the irc conversation."""

_TIMEOUT_TXT = """Max time for fetch operations (seconds). A value of 0
disables timeout for this repo completely"""


_REPO_OPTIONS = {
    'url':
        lambda: registry.String('', _URL_TEXT),
    'channels':
        lambda: registry.SpaceSeparatedListOfStrings('', _CHANNELS_TXT),
    'branches':
        lambda: registry.String('*', _BRANCHES_TXT),
    'commitMessage1':
        lambda: registry.String('[%n|%b|%a] %m', _MESSAGE1_TXT),
    'commitMessage2':
        lambda: registry.String('', _MESSAGE2_TXT),
    'snarfMessage1':
        lambda: registry.String('I. e., [%n|%a] %m', _SNARFMSG1_TXT),
    'snarfMessage2':
        lambda: registry.String('', _SNARFMSG2_TXT),
    'enableSnarf':
        lambda: registry.Boolean(True, _SNARF_TXT),
    'groupHeader':
        lambda: registry.Boolean(True, _GROUP_HDR_TXT),
    'fetchTimeout':
        lambda: registry.Integer(60, _TIMEOUT_TXT),
}


def global_option(option):
    ''' Return an overall plugin option (registered at load time). '''
    return conf.supybot.plugins.get('git').get(option)


def repo_option(reponame, option):
    ''' Return a repo-specific option, registering on the fly. '''
    repos = global_option('repos')
    try:
        repo = repos.get(reponame)
    except registry.NonExistentRegistryEntry:
        repo = conf.registerGroup(repos, reponame)
    try:
        return repo.get(option)
    except registry.NonExistentRegistryEntry:
        conf.registerGlobalValue(repo, option, _REPO_OPTIONS[option]())
        return repo.get(option)


def unregister_repo(reponame):
    ''' Unregister  repository from registry. '''
    try:
        global_option('repos').unregister(reponame)
    except registry.NonExistentRegistryEntry:
        pass


def configure(advanced):
    '''
    This will be called by supybot to configure this module.  advanced is
    a bool that specifies whether the user identified himself as an advanced
    user or not.  You should effect your configuration by manipulating the
    registry as appropriate.
    '''
    from supybot.questions import expect, anything, something, yn
    conf.registerPlugin('Git', True)


Git = conf.registerPlugin('Git')

conf.registerGroup(Git, 'repos',
    help = "Internal list of repositories (hands off, please).")

conf.registerGlobalValue(Git, 'repolist',
        registry.SpaceSeparatedListOfStrings([],
           "Internal list of configured repos, please don't touch "))

conf.registerGlobalValue(Git, 'repoDir',
    registry.String('git_repositories', """The path where local copies of
    repositories will be kept. Relative paths are interpreted from
    supybot's startup directory."""))

conf.registerGlobalValue(Git, 'pollPeriod',
    registry.NonNegativeInteger(120, """ How often (in seconds) that
  repositories will be polled for changes. Zero disables periodic polling.
  If you change the value from zero to a positive value, call `rehash` to
  restart polling."""))

conf.registerGlobalValue(Git, 'maxCommitsAtOnce',
    registry.NonNegativeInteger(5, """Limit how many commits can be displayed
  in one update. This will affect output from the periodic polling as well
  as the log command"""))

conf.registerGlobalValue(Git, 'fetchTimeout',
    registry.NonNegativeInteger(300, """Max time for fetch operations
       (seconds)."""))

# vim:set shiftwidth=4 tabstop=4 expandtab textwidth=79:
