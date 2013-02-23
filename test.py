# Copyright (c) 2011-2012, Mike Mueller
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#   * Do whatever you want.
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

from supybot.test import *
from supybot import conf

from mock import Mock, patch
import git
import os
import time

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SRC_DIR, 'test-data')

# This timeout value works for me and keeps the tests snappy. If test queries
# are not getting responses, you may need to bump this higher.
LOOP_TIMEOUT = 0.1

# Global mocks
git.Git.clone = Mock()
git.Repo = Mock()

# A pile of commits for use wherever (most recent first)
COMMITS = [Mock(), Mock(), Mock(), Mock(), Mock()]
COMMITS[0].author.name = 'nstark'
COMMITS[0].hexsha = 'abcdefabcdefabcdefabcdefabcdefabcdefabcd'
COMMITS[0].message = 'Fix bugs.'
COMMITS[1].author.name = 'tlannister'
COMMITS[1].hexsha = 'abcdefabcdefabcdefabcdefabcdefabcdefabcd'
COMMITS[1].message = 'I am more long-winded\nand may even use newlines.'
COMMITS[2].author.name = 'tlannister'
COMMITS[2].hexsha = 'abcdefabcdefabcdefabcdefabcdefabcdefabcd'
COMMITS[2].message = 'Snarks and grumpkins'
COMMITS[3].author.name = 'jsnow'
COMMITS[3].hexsha = 'abcdefabcdefabcdefabcdefabcdefabcdefabcd'
COMMITS[3].message = "Finished brooding, think I'll go brood."
COMMITS[4].author.name = 'tlannister'
COMMITS[4].hexsha = 'deadbeefcdefabcdefabcdefabcdefabcdefabcd'
COMMITS[4].message = "I'm the only one getting things done."

# Workaround Supybot 0.83.4.1 bug with Owner treating 'log' as a command
conf.registerGlobalValue(conf.supybot.commands.defaultPlugins,
                         'log', registry.String('Git', ''))
conf.supybot.commands.defaultPlugins.get('log').set('Git')

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
        self.assertEqual(responses, expectedResponses,
                         '\nActual:\n%s\n\nExpected:\n%s' %
                         ('\n'.join(responses), '\n'.join(expectedResponses)))
        return responses


class GitRehashTest(PluginTestCase):
    plugins = ('Git',)

    def setUp(self, nick='test'):
        self._metamock = patch('git.Repo')
        self.Repo = self._metamock.__enter__()
        self.Repo.return_value = self.Repo
        self.Repo.iter_commits.return_value = COMMITS
        super(GitRehashTest, self).setUp()
        conf.supybot.plugins.Git.pollPeriod.setValue(0)

    def testRehashEmpty(self):
        conf.supybot.plugins.Git.configFile.setValue(DATA_DIR + '/empty.ini')
        self.assertResponse('rehash', 'Git reinitialized with 0 repository.')

    def testRehashOne(self):
        self._metamock = patch('__builtin__.list')
        conf.supybot.plugins.Git.configFile.setValue(DATA_DIR + '/one.ini')
        self.assertResponse('rehash', 'Git reinitialized with 1 repository.')


class GitRepositoryListTest(ChannelPluginTestCase, PluginTestCaseUtilMixin):
    channel = '#test'
    plugins = ('Git',)

    def setUp(self):
        self._metamock = patch('git.Repo')
        self.Repo = self._metamock.__enter__()
        super(GitRepositoryListTest, self).setUp()
        ini = os.path.join(DATA_DIR, 'multi-channel.ini')
        conf.supybot.plugins.Git.pollPeriod.setValue(0)
        conf.supybot.plugins.Git.configFile.setValue(ini)
        self.assertResponse('rehash', 'Git reinitialized with 3 repositories.')

    def testRepositoryList(self):
        expected = [
            '\x02test1\x02 (Test Repository 1)' +
                ' /somewhere/to/nowhere 1 branch',
            '\x02test2\x02 (Test Repository 2)' +
                ' /somewhere/to/nowhere 1 branch',
        ]
        self.assertResponses('repositories', expected)


class GitNoAccessTest(ChannelPluginTestCase, PluginTestCaseUtilMixin):
    channel = '#unused'
    plugins = ('Git',)

    def setUp(self):
        self._metamock = patch('git.Repo')
        self.Repo = self._metamock.__enter__()
        super(GitNoAccessTest, self).setUp()
        ini = os.path.join(DATA_DIR, 'multi-channel.ini')
        conf.supybot.plugins.Git.pollPeriod.setValue(0)
        conf.supybot.plugins.Git.configFile.setValue(ini)
        self.assertResponse('rehash', 'Git reinitialized with 3 repositories.')

    def testRepositoryListNoAccess(self):
        expected = ['No repositories configured for this channel.']
        self.assertResponses('repositories', expected)

    def testLogNoAccess(self):
        expected = ['Sorry, not allowed in this channel.']
        self.assertResponses('repolog test1', expected)


class GitLogTest(ChannelPluginTestCase, PluginTestCaseUtilMixin):
    channel = '#somewhere'
    plugins = ('Git',)

    def setUp(self):
        self._metamock = patch('git.Repo')
        self.Repo = self._metamock.__enter__()
        self.Repo.return_value = self.Repo
        self.Repo.iter_commits.return_value = COMMITS
        if self._testMethodName in ['testLogNotAllowed',
                                    'testLogNegative',
                                    'testLogZero']:
            os.environ['MOCK_TEST_BRANCHES'] = 'master'
        elif self._testMethodName in ['testLogOne',
                                      'testLogTwo',
                                      'testLogFive',
                                      'testSnarf']:
            os.environ['MOCK_TEST_BRANCHES'] = 'feature'
        elif 'MOCK_TEST_BRANCHES' in os.environ:
            del(os.environ['MOCK_TEST_BRANCHES'])
        super(GitLogTest, self).setUp()

        ini = os.path.join(DATA_DIR, 'multi-channel.ini')
        conf.supybot.plugins.Git.pollPeriod.setValue(0)
        conf.supybot.plugins.Git.maxCommitsAtOnce.setValue(3)
        conf.supybot.plugins.Git.configFile.setValue(ini)
        self.assertResponse('rehash', 'Git reinitialized with 3 repositories.')

    def tearDown(self):
        del self.Repo
        self._metamock.__exit__()

    def testLogNonexistent(self):
        expected = ['No repository named nothing, showing available:',
            '\x02test2\x02 (Test Repository 2) ' +
                '/somewhere/to/nowhere 0 branch',
            '\x02test3\x02 (Test Repository 3) ' +
                '/somewhere/to/nowhere 0 branch']
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
        expected = ['[test2|feature|nstark] Fix bugs.']
        self.assertResponses('repolog test2 feature', expected)

    def testLogTwo(self):
        expected = [
            '[test2|feature|tlannister] I am more long-winded',
            '[test2|feature|nstark] Fix bugs.',
        ]
        self.assertResponses('repolog test2 feature 2', expected)

    def testLogFive(self):
        expected = [
            'Showing latest 3 of 5 commits to Test Repository 2...',
            '[test2|feature|tlannister] Snarks and grumpkins',
            '[test2|feature|tlannister] I am more long-winded',
            '[test2|feature|nstark] Fix bugs.',
        ]
        self.assertResponses('repolog test2 feature 5', expected)

    def testSnarf(self):
        self.Repo.commit.return_value = COMMITS[4]
        expected = [
            "Talking about deadbee?",
            "[test2|unknown|tlannister] I'm the only one getting things done.",
        ]
        self.assertResponses('who wants some deadbeef?', expected,
                             usePrefixChar=False)


# vim:set shiftwidth=4 tabstop=4 expandtab textwidth=79:
