###
# Copyright (c) 2009, Mike Mueller
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

''' Overall configuration reflecting supybot.git.* config variables. '''

# pylint: disable=W0612

import supybot.conf as conf
import supybot.registry as registry


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

conf.registerGroup(Git, 'repos')
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
