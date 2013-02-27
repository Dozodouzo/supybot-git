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
* Moved all configuration to the supybot config system (the git.ini
  file is no more)
* To support multiple branches and configuration several commands has
  been changed. Notably there are new commands to create and destroy
  repositories. Several command have been renamed, most to repo.. names
  like repoadd, repolog, repolist in an attempt to make them easy to
  remember and less likely to clash with other plugins.
* The logging has been fixed, upstream is broken and does not respect
  configuration. Added stacktraces to some exception handling.
* Backwards compatibility has been dropped: GitPython 0.1 is not supported,
  some old commands are not defined, compatility stuff in config is dropped.
* Static checking using pylint and pep8 has been added.
* Code has been reorganized to a hopefully more consistent shape.
* The initial cloning of the git repository has been moved to the
  explicit repoadd command.
* A timeout is used to complete otherwise hanging fetch operations. The
  thread design has been revised removing busy-wait and improving
  scheduling
* The enableSnarf configuration value is now defined per repo, not as an
  overall value.
* This README has been uodated, notably with a "Getting Started" section.

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

* GitPython (vers 0.3.x required)

Dependencies are also listed in `requirements.txt`.  You can install them with
the command `pip install -r requirements.txt`.

Getting started
---------------
* Refer to the supybot documentation to install supybot and configure
  your server e. g., using subybot-wizard. Verify that you can start and
  contact your bot.

* Unpack the plugin into the plugins directory (created by
  supybot-wizard):
```
      $ cd plugins
      $ git clone https://github.com/leamas/supybot-git Git
```

* Restart the server and use @list to verify that the plugin is loaded:
```
    <leamas> @list
    <al-bot-test> leamas: Admin, Channel, Config, Git, Owner, and User
```

* Identify yourself for the bot in a *private window*. Creating user +
  password is part of the supybot-wizard process.
```
     <leamas> identify al my-secret-pw
     <al-bot-test> The operation succeeded.
```

* Define your first directory, using a a repository you have access to and
  a channel you want to feed e. g.,
```
    <leamas> @repoadd leamas-git https://github.com/leamas/supybot-git #al-bot-test
    <al-bot-test> leamas: Repository created and cloned
```

* Initially you will follow all branches (the 'branches' config item is '\*') Use
  the branches command to see branches in you repo:
```
    <leamas> @branches leamas-git
    <al-bot-test> leamas: Watched branches: master, devel
```

* If you commit and push something to your repository you will see the
  commits in the channel:
```
    <al-bot-test> Alec Leamas pushed 3 commit(s) to devel at leamas-git
    <al-bot-test> [leamas-git|devel|Alec Leamas] Adapt tests for no ini-file
    <al-bot-test> [leamas-git|devel|Alec Leamas] Remove INI-file, use registry instead
    <al-bot-test> [leamas-git|devel|Alec Leamas] Doc update
```

* If a commit is mentioned in a conversation the bot will provide info on it.
```
    <leamas> what about 15a74ae?
    <al-bot-test> Talking about 15a74ae?
    <al-bot-test> [leamas-git|unknown|Alec Leamas] Adapt tests for no ini-file
```

Configuration
-------------

The configuration is done completely in the supybot registry. There are general
settings and repository specific ones.

To see the general settings:
```
    @config list plugins.git
    leamas: @repos, fetchTimeout, maxCommitsAtOnce,
    pollPeriod, public, repoDir, and repolist
```

Each setting has help info and could be inspected and set using the config
plugin, see it's documents. Quick crash course using enableSnarf as example:
* Getting help: @config help plugins.git.enableSnarf
* See actual value: @config  plugins.git.enableSnarf
* Setting value: @config  plugins.git.enableSnarf True

The available repos can be listed using
```
    @config list plugins.git.repos
    leamas: @test1, @test2, and @test3
```

The settings for each repo is below these. To see available settings:
```
    @config list plugins.git.repos.test1
    leamas: branches, channels, commitMessage1, commitMessage2, enableSnarf,
    groupHeader, name, and url
```

These variables can be manipulated using the @config command in the same way.
NOTE! After modifying the variables using @reload git to make them effective.


Commit Messages
---------------

Commit messages are produced from a general format string that you define.
in the commitMessage1 and  commitMessage2 configuration item (see above).
They use the following substitution parameters:

    %a       Author name
    %b       Branch being watched
    %c       Commit SHA (first 7 digits)
    %C       Commit SHA (entire 40 digits)
    %e       Author email
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

    commitMessage1 = %![%!%(14)%s%(15)%!|%!%(14)%b%(15)%!|%!%(14)%a%(15)%!]%! %m
    commitMessage2 = View%!:%! %(4)%l

As noted above, the default is a simpler version of this:

    commitMessage1 = [%s|%b|%a] %m
    commitMessage2 = '' (unset)

Leading spaces in any message line are discarded.

As mentioned above, there are a few things that can be configured within the
Supybot configuration framework.  For relative paths, they are relative to
where Supybot is invoked.  If you're unsure what that might be, just set them
to absolute paths.  The settings are found within `supybot.plugins.Git`:

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

When a repository is created it's also cloned. After this, a
thread fetches changes from the remote repo periodically.

**Warning #1:** If the repository is big and/or the network is slow, the
first load may take a very long time!

**Warning #2:** If the repositories you track are big, this plugin will use a
lot of disk space for its local clones.

After this, a  poll operation runs (generally pretty quick), including
a check for any commits that arrived since the last check.

Repository clones are never deleted. If you decide to stop tracking one, you
may want to go manually delete it to free up disk space.

Command List
------------

* `repolog`: Takes a repository nickname, a branch  and an optional
  count parameter (default 1).  Shows the last n commits on that branch
  Only works if the repository is configured for the current channel.

* `repolist`: List any known repositories configured for the current
  channel.

* `branches`: Lists tracked branches for a given repository.

* `rehash`: Reload configuraiton, restarts any polling if applicable.

* 'repoadd`: Adds a new repo given it's name, an url and one or more channels
  which should be informed. The url might be a relative path, interpreted from
  supybot's start directory.

* `repokill`: Remove an  existing repository given it's name.

As usual with Supybot plugins, you can call these commands by themselves or
with the plugin name prefix, e.g. `@git rehash`.  The latter form is only
necessary if another plugin has a command called `rehash` as well, causing a
conflict.


Static checking & unit tests
----------------------------

pep8 (in the Git directory):
```
  $ pep8 --config pep8.conf . > pep8.log
```
pylint: (in the Git directory):
```
  $ pylint --rcfile pylint.conf \*.py > pylint.log
```
unit tests - run in supybot home directory
```
  $ pushd plugins/Git/testdata
  $ tar xzf git-repo.tar.gz
  $ popd
  $ supybot-test  plugins/Git
```



