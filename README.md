Leamas's supybot-git fork
-------------------------

This branch (master) contains some commits which have been sent as a
pull request upstream. I have continued the work in the devel branch.
=======
Leamas supybot-git fork
=======================

For the moment, this is a fork of Mike Muellers excellent work at
https://github.com/mmueller/supybot-git. For better or worse I have
modified the code:
* Made it possible to listen to several branches in the same repo
  definition.
* Added an optional group header printed before groups of lines.
* To support multiple branches configuration and several commands has
  been changed.
* The 'log' command has been renamed to 'repolog'. Maintaining the
  'log' name requires some horrible tweaks, and it's anyway likely
  to clash with other plugins beeing too generic.
* The logging has been fixed, upstream is broken and does not respect
  configuration. Added stacktraces to some exception handling.
* Backwards compatibilty has been dropped: GitPython 0.1 is not supported,
  some old commands are not defined.
* Static checking using pylint and pep8 has been added.
* Code has been reorganized to a hopefully more consistent shape.

There's a pull request at Mike's repo pending. Depending on the outcome of
that this will be long-time separate fork or not.

--- end of Alec's addendum

Supybot Git Plugin
==================
This is a plugin for the IRC bot Supybot that introduces the ability to
monitor Git repositories.  Features:

* Notifies IRC channel of new commits.
* Display a log of recent commits on command.
* Monitor as many repository/branch combinations as you like.
* Privacy: repositories are associated with a channel and cannot be seen from
  other channels.
* Highly configurable.

NEWS
----

### November 17, 2012

Interface changes:

* Several commands have been renamed.  Sorry for the inconvenience, but it was
  time to make some common sense usabliity improvements.
* Repository definitions now take a `channels` option instead of a single
  `channel` (although `channel` is supported for backwards compatibility).

Dependencies
------------

This plugin depends on the Python packages:

* GitPython (supports 0.1.x and 0.3.x)
* Mock (if you want to run the tests)

Dependencies are also listed in `requirements.txt`.  You can install them with
the command `pip install -r requirements.txt`.

Configuration
-------------

The configuration is done completely in the supybot registry. There are general
settings and repository specific ones.

To see the general settings:
    @config list plugins.git
    leamas: @repos, configFile, enableSnarf, fetchTimeout, maxCommitsAtOnce,
    pollPeriod, public, repoDir, and repolist

Each settins has help info (@config help plugins.git.enableSnarf), and could be
inspected and set using the @config plugin, see it's documents

The available repos can be listed using
    @config list plugins.git.repos
    leamas: @test1, @test2, and @test3

The settings for each repo is below these. To see available settings:
    @config list plugins.git.repos.test1
    leamas: branches, channels, commitLink, commitMessage, enableSnarf,
    groupHeader, name, and url

These variables can be manipulated using the @config command in the same way.
After modifying thee variables using @reload git to make them effective.


Commit Messages
---------------

Commit messages are produced from a general format string that you define.
It uses the following substitution parameters:

    %a       Author name
    %b       Branch being watched
    %c       Commit SHA (first 7 digits)
    %C       Commit SHA (entire 40 digits)
    %e       Author email
    %l       Link to view commit on the web
    %m       Commit message (first line only)
    %n       Name of repository
    %u       Git URL for repository
    %(fg)    IRC color code (foreground only)
    %(fg,bg) IRC color code (foreground and background)
    %!       Toggle bold
    %r       Reset text color and attributes
    %S       Single space, only meaningful at line start.
    %%       A literal percent sign.

The format string can span multiple lines, in which case, the plugin will
output multiple messages per commit.  Here is a format string that I am
partial to:

    commit message = %![%!%(14)%s%(15)%!|%!%(14)%b%(15)%!|%!%(14)%a%(15)%!]%! %m
                     View%!:%! %(4)%l

As noted above, the default is a simpler version of this:

    commit message = [%s|%b|%a] %m

Leading spaces in any line of the message are discarded, so you can format it
nicely in the file.


As mentioned above, there are a few things that can be configured within the
Supybot configuration framework.  For relative paths, they are relative to
where Supybot is invoked.  If you're unsure what that might be, just set them
to absolute paths.  The settings are found within `supybot.plugins.Git`:

* `configFile`: Path to the INI file.  Default: git.ini

* `repoDir`: Path where local clones of repositories will be kept.  This is a
  directory that will contain a copy of all repository being tracked.
  Default: git\_repositories

* `pollPeriod`: How often (in seconds) that repositories will be polled for
  changes.  Zero disables periodic polling.  If you change the value from zero
  to a positive value, call `rehash` to restart polling. Default: 120

* `maxCommitsAtOnce`: Limit how many commits can be displayed in one update.
  This will affect output from the periodic polling as well as the log
  command.  Default: 5

How Notification Works
----------------------

The first time a repository is created it's also cloned.

**Warning #1:** If the repository is big and/or the network is slow, the
first load may take a very long time!

**Warning #2:** If the repositories you track are big, this plugin will use a
lot of disk space for its local clones.

After this, the poll operation involves a fetch (generally pretty quick), and
then a check for any commits that arrived since the last check.

Repository clones are never deleted. If you decide to stop tracking one, you
may want to go manually delete it to free up disk space.

Command List
------------

* `repolog`: Takes a repository nickname, a branch  and an optional
  count parameter (default 1).  Shows the last n commits on the branches
  tracked for that repository.  Only works if the repository is configured
  for the current channel.

* `repolist`: List any known repositories configured for the current
  channel.

* `branches`: Lists tracked branches for a given repository.

* `rehash`: Reload the INI file, cloning any newly present repositories.
  Restarts any polling if applicable.

* 'repoadd`: Adds a new repo given it's name, an url and one or more channels
  which should be informed. The url might be a relative path, interpreted from
  supybot's start directory.

* `repokill`: Remove an  existing repository given it's name.

As usual with Supybot plugins, you can call these commands by themselves or
with the plugin name prefix, e.g. `@git log`.  The latter form is only
necessary if another plugin has a command called `log` as well, causing a
conflict.


Static checking & unit tests
----------------------------

pep8:

  $ pep8 --config pep8.conf . > pep8.log

pylint:

  $ pylint --rcfile pylint.conf *.py > pylint.log

unit tests - run in supybot config directory

  $ supybot-test  --plugins-dir plugins



