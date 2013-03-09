# Copyright (c) 2011-2012, Mike Mueller
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

# Unused wildcard imports:
# pylint: disable=W0614,W0401
# Missing docstrings:
# pylint: disable=C0111
# supybot's typenames are irregular
# pylint: disable=C0103
# Too many public methods:
# pylint: disable=R0904

# http://sourceforge.net/apps/mediawiki/gribble/index.php?title=Plugin_testing

from supybot.test import *
from supybot import conf

import git
import os
import time

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SRC_DIR, 'test-data')

# This timeout value works for me and keeps the tests snappy. If test queries
# are not getting responses, you may need to bump this higher.
LOOP_TIMEOUT = 0.1


# Pre-test checks
GIT_API_VERSION = int(git.__version__[2])
assert GIT_API_VERSION == 3, 'Tests only run against GitPython 0.3.x+ API.'


class PluginTestCaseUtilMixin(object):
    "Some additional utilities used in this plugin's tests."

    def _feedMsgLoop(self, query, timeout_=None, **kwargs):
        "Send a message and wait for a list of responses instead of just one."
        if timeout_ is None:
            timeout_ = LOOP_TIMEOUT
        responses = []
        start = time.time()
        r = self._feedMsg(query, timeout=timeout_, **kwargs)
        # Sleep off remaining time, then start sending empty queries until
        # the replies stop coming.
        remainder = timeout_ - (time.time() - start)
        time.sleep(remainder if remainder > 0 else 0)
        query = conf.supybot.reply.whenAddressedBy.chars()[0]
        while r:
            responses.append(r)
            r = self._feedMsg(query, timeout=0, **kwargs)
        return responses

    def assertResponses(self, query, expectedResponses, **kwargs):
        "Run a command and assert that it returns the given list of replies."
        responses = self._feedMsgLoop(query, **kwargs)
        responses = map(lambda m: m.args[1], responses)
        self.assertEqual(sorted(responses), sorted(expectedResponses),
                         '\nActual:\n%s\n\nExpected:\n%s' %
                         ('\n'.join(responses), '\n'.join(expectedResponses)))
        return responses

    def clear_repos(self):
        "Remove all defined repositories."
        plugin_group = conf.supybot.plugins.get('Git')
        try:
            plugin_group.unregister('repos')
        except registry.NonExistentRegistryEntry:
            pass
        conf.registerGroup(plugin_group, 'repos')
        conf.supybot.plugins.Git.repolist.setValue('')
        self.assertNotError('reload Git')
        expected = ['The operation succeeded.',
                    'Git reinitialized with 0 repositories.',
                    'The operation succeeded.'
        ]
        self.assertResponses('reload Git', expected)


class GitReloadTest(ChannelPluginTestCase, PluginTestCaseUtilMixin):
    plugins = ('Git', 'User')

    def setUp(self, nick='test'):      # pylint: disable=W0221
        ChannelPluginTestCase.setUp(self)
        self.clear_repos()
        conf.supybot.plugins.Git.pollPeriod.setValue(0)
        self.assertNotError('register suptest suptest', private=True)

    def testReloadEmpty(self):
        expected = ['Git reinitialized with 0 repositories.',
                    'The operation succeeded.'
        ]
        self.assertResponses('reload Git', expected)

    def testReloadOne(self):
        self.assertNotError('identify suptest suptest', private=True)
        self.assertResponse(
            'repoadd test7 plugins/Git/test-data/git-repo #test',
            'Repository created and cloned')
        self.getMsg(' ')
        expected = ['Git reinitialized with 1 repository.',
                    'The operation succeeded.'
        ]
        self.assertResponses('reload Git', expected)


class GitRepositoryListTest(ChannelPluginTestCase, PluginTestCaseUtilMixin):
    channel = '#test'
    plugins = ('Git', 'User', 'Config')

    def setUp(self):
        ChannelPluginTestCase.setUp(self)
        self.clear_repos()
        conf.supybot.plugins.Git.pollPeriod.setValue(0)
        self.assertNotError(
            'repoadd test1 plugins/Git/test-data/git-repo #test')
        self.getMsg(' ')
        self.assertNotError(
            'repoadd test2 plugins/Git/test-data/git-repo #test')
        self.getMsg(' ')
        self.assertNotError(
            'repoadd test3 plugins/Git/test-data/git-repo #test')
        self.getMsg(' ')
        expected = ['Git reinitialized with 3 repositories.',
                    'The operation succeeded.'
        ]
        self.assertResponses('reload Git', expected)

    def testRepositoryList(self):
        expected = [
            '\x02test1\x02  plugins/Git/test-data/git-repo 4 branches',
            '\x02test2\x02  plugins/Git/test-data/git-repo 4 branches',
            '\x02test3\x02  plugins/Git/test-data/git-repo 4 branches',
        ]
        self.assertResponses('repolist', expected)


class GitNoAccessTest(ChannelPluginTestCase, PluginTestCaseUtilMixin):
    channel = '#unused'
    plugins = ('Git',)

    def setUp(self):
        ChannelPluginTestCase.setUp(self)
        self.clear_repos()
        conf.supybot.plugins.Git.pollPeriod.setValue(0)
        self.assertNotError(
            'repoadd test1 plugins/Git/test-data/git-repo #test')
        self.getMsg(' ')
        self.assertNotError(
            'repoadd test2 plugins/Git/test-data/git-repo #test')
        self.getMsg(' ')
        self.assertNotError(
            'repoadd test3 plugins/Git/test-data/git-repo #test')
        self.getMsg(' ')
        expected = ['Git reinitialized with 3 repositories.',
                    'The operation succeeded.'
        ]
        self.assertResponses('reload Git', expected)

    def testRepositoryListNoAccess(self):
        expected = ['No repositories configured for this channel.']
        self.assertResponses('repolist', expected)

    def testLogNoAccess(self):
        expected = ['Sorry, not allowed in this channel.']
        self.assertResponses('repolog test1', expected)


class GitLogTest(ChannelPluginTestCase, PluginTestCaseUtilMixin):
    channel = '#test'
    plugins = ('Git',)

    def setUp(self):
        ChannelPluginTestCase.setUp(self)
        conf.supybot.plugins.Git.pollPeriod.setValue(0)
        conf.supybot.plugins.Git.maxCommitsAtOnce.setValue(3)
        self.clear_repos()
        self.assertNotError(
            'repoadd test1 plugins/Git/test-data/git-repo #unavailable')
        self.getMsg(' ')
        self.assertNotError(
            'repoadd test2 plugins/Git/test-data/git-repo #test')
        self.getMsg(' ')
        expected = ['Git reinitialized with 2 repositories.',
                    'The operation succeeded.'
        ]
        self.assertResponses('reload Git', expected)

    def testLogNonexistent(self):
        expected = ['No repository named nothing, showing available:',
            '\x02test2\x02  plugins/Git/test-data/git-repo 4 branches']
        self.assertResponses('repolog nothing', expected)

    def testLogNotAllowed(self):
        expected = ['Sorry, not allowed in this channel.']
        self.assertResponses('repolog test1', expected)

    def testLogZero(self):
        expected = [
            "(\x02repolog repo [branch [count]]\x02) -- Display the last " +
            "commits on the named repository. branch defaults to " +
            "'master', count defaults to 1 if unspecified."
        ]
        self.assertResponses('repolog test2 master 0', expected)

    def testLogNegative(self):
        expected = [
            '(\x02repolog repo [branch [count]]\x02) -- Display the last ' +
            "commits on the named repository. branch defaults to " +
            "'master', count defaults to 1 if unspecified."
        ]
        self.assertResponses('repolog test2 master -1', expected)

    def testLogOne(self):
        expected = ['[test2|feature|Tyrion Lannister] Snarks and grumpkins']
        self.assertResponses('repolog test2 feature', expected)

    def testLogTwo(self):
        expected = [
            '[test2|feature|Tyrion Lannister] I am more long-winded',
            '[test2|feature|Tyrion Lannister] Snarks and grumpkins',
        ]
        self.assertResponses('repolog test2 feature 2', expected)

    def testLogFive(self):
        expected = [
            'Showing latest 3 of 5 commits to test2...',
            '[test2|feature|Tyrion Lannister] I am more long-winded',
            '[test2|feature|Tyrion Lannister] Snarks and grumpkins',
            '[test2|feature|Ned Stark] Fix bugs.',
        ]
        self.assertResponses('repolog test2 feature 5', expected)

    def testSnarf(self):
        expected = [
            "Talking about cbe46d8?",
            "I. e., [test2|Tyrion Lannister]"
                " I am the only one getting things done",
        ]
        self.assertResponses('What about cbe46d8?', expected,
                             usePrefixChar=False)


class GitKillTest(ChannelPluginTestCase, PluginTestCaseUtilMixin):
    channel = '#test'
    plugins = ('Git',)

    def setUp(self):
        ChannelPluginTestCase.setUp(self)
        conf.supybot.plugins.Git.pollPeriod.setValue(0)
        conf.supybot.plugins.Git.maxCommitsAtOnce.setValue(3)
        self.clear_repos()
        self.assertNotError(
            'repoadd test1 plugins/Git/test-data/git-repo #unavailable')
        self.getMsg(' ')
        self.assertNotError(
            'repoadd test2 plugins/Git/test-data/git-repo #test')
        self.getMsg(' ')
        expected = ['Git reinitialized with 2 repositories.',
                    'The operation succeeded.'
        ]
        self.assertResponses('reload Git', expected)

    def testKillNonexistent(self):
        expected = ['No repository named nothing, showing available:',
                    '\x02test2\x02  plugins/Git/test-data/git-repo 4 branches']
        self.assertResponses('repolog nothing', expected)
        expected = ['Git reinitialized with 2 repositories.',
                    'The operation succeeded.'
        ]
        self.assertResponses('reload Git', expected)

    def testKillBadChannel(self):
        expected = 'Repository deleted'
        self.assertResponse('repokill test1', expected)
        expected = ['Git reinitialized with 1 repository.',
                    'The operation succeeded.'
        ]
        self.assertResponses('reload Git', expected)

    def testKill(self):
        expected = "Repository deleted"
        self.assertResponse('repokill test2', expected)
        expected = ['Git reinitialized with 1 repository.',
                    'The operation succeeded.'
        ]
        self.assertResponses('reload Git', expected)


class GitBranchTest(ChannelPluginTestCase, PluginTestCaseUtilMixin):
    channel = '#test'
    plugins = ('Git',)

    def setUp(self):
        ChannelPluginTestCase.setUp(self)
        conf.supybot.plugins.Git.pollPeriod.setValue(0)
        conf.supybot.plugins.Git.maxCommitsAtOnce.setValue(3)
        self.clear_repos()
        self.assertNotError(
            'repoadd test1 plugins/Git/test-data/git-repo #unavailable')
        self.getMsg(' ')
        self.assertNotError(
            'repoadd test2 plugins/Git/test-data/git-repo #test')
        self.getMsg(' ')
        expected = ['Git reinitialized with 2 repositories.',
                    'The operation succeeded.'
        ]
        self.assertResponses('reload Git', expected)

    def testBranchNonexistent(self):
        expected = ['No repository named nothing, showing available:',
            '\x02test2\x02  plugins/Git/test-data/git-repo 4 branches']
        self.assertResponses('repostat nothing', expected)

    def testBranchNotAllowed(self):
        expected = 'Sorry, not allowed in this channel.'
        self.assertResponse('repostat test1', expected)

    def testBranch(self):
        expected = 'Watched branches: test1, test2, master, feature'
        self.assertResponse('repostat test2', expected)



# vim:set shiftwidth=4 tabstop=4 expandtab textwidth=79:
