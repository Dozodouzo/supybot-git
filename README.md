Supybot Git Plugin
==================
This is a plugin for the IRC bot Supybot that introduces the ability to
monitor Git repositories.  Features:

* Notifies IRC channel of new commits.
* Reports info on commit SHA:s mentioned in IRC conversations.
* Display a log of recent commits on command.
* Monitor as many repository/branch combinations as you like.
* Privacy: repositories are associated with a channel and cannot be seen from
  other channels.
* Highly configurable.

NEWS
----

### March 19, 2013
* supybot-git is now in Fedora! The package has landed in Fedora-17, Fedora-18
  and the upcoming Fedora-19 and can be installed using the usual package
  tools.
* After discussion with Mike Mueller the plugin is relicensed using the original
  BSD terms.

### March 5, 2013

* I (i. e., Alec Leamas) forked Mike's original work. Mike and I have agreed on
  not merging this fork with Mike's so this fork will be maintained separately.
* It's now possible to track several (by default all) branches in a repo.
* All configuration is done in supybot's config system, see Configuration below
  (no git.ini file anymore).
* A group header has been added, see screenshots at
  https://github.com/mmueller/supybot-git/pull/14.
* New command names (see Command List below).
* Internally code has improved logging, static checking, improved and simplified
  threading model, and some other refactoring.
* Plugin now requires GitPythin 0.3.x  (0.1 compatibility is dropped).


### November 17, 2012

Interface changes:

* Several commands have been renamed.  Sorry for the inconvenience, but it was
  time to make some common sense usability improvements.
* Repository definitions now take a `channels` option instead of a single
  `channel`.

Dependencies
------------

This plugin depends on the Python packages:

* GitPython (vers 0.3.x required)

Dependencies are also listed in `requirements.txt`.  You can install them with
the command `pip install -r requirements.txt`.

Getting started
---------------
* Refer to the supybot documentation to install supybot and configure
  your server e. g., using supybot-wizard. Verify that you can start and
  contact your bot.

* On Fedora, you can just install the supybot-git package and proceed to
  next step. Otherwise unpack the plugin into the plugins directory
  (created by supybot-wizard):
```
      $ cd plugins
      $ git clone https://github.com/leamas/supybot-git Git
```

* Load the plugin and use `@list` to verify (restarting server should
  also load the plugin)
```
    <leamas> @load Git
    <al-bot-test> The operation succeeded.
    <leamas> @list
    <al-bot-test> leamas: Admin, Channel, Config, Git, Owner, and User
```

* Identify yourself for the bot in a *private window*. Creating user +
  password is part of the supybot-wizard process.
```
     <leamas> identify al my-secret-pw
     <al-bot-test> The operation succeeded.
```

* Define your first repo, using a repository you have access to and
  a channel you want to feed e. g.,
```
    <leamas> @repoadd leamas-git https://github.com/leamas/supybot-git #al-bot-test
    <al-bot-test> leamas: Cloning of leamas-git started...
    <al-bot-test> leamas: Repository created and cloned
```

* Initially you will follow all branches (the 'branches' config item is '\*') Use
  the `@repostat` command to see branches in you repo:
```
    <leamas> @repostat leamas-git
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
    <al-bot-test> I. e., [leamas-git|unknown|Alec Leamas] Adapt tests for no ini-file
```

Configuration
-------------

The configuration is done completely in the supybot registry. There are general
settings and repository specific ones.

To see the general settings:
```
    @config list plugins.git
    leamas: @repos, maxCommitsAtOnce, pollPeriod, public, repoDir, and repolist
```

Each setting has help info and could be inspected and set using the config
plugin, see it's documents. Quick crash course using pollPeriod as example:
* Getting help: `@config help plugins.git.pollPeriod`
* See actual value: `@config plugins.git.pollPeriod`
* Setting value: `@config plugins.git.pollPeriod 60`

The `public` and `repolist` options are internal, please don't touch.

The available repos can be listed using
```
    @config list plugins.git.repos
    leamas: @test1, @test2, and @test3
```

Settings for each repo are below these. To see available settings:
```
    @config list plugins.git.repos.test1
    leamas: branches, channels, commitMessage1, commitMessage2, enableSnarf,
    fetchTimeout, groupHeader, name, snarfMessage1, snarfMessage2, and url
```

These variables can be manipulated using the @config command in the same way.
NOTE! After modifying the variables use `@reload Git` to make them effective.

It's possible to edit the config file "by hand" as described in documentation
for @config. However, structural changes is better done by `repoadd` and
`repokill` even if the config  file is edited after that.


Commit Messages
---------------

Commit  and snarf messages are produced from a general format string that
you define in the commitMessage1, commitMessage2, snarfMessage1 and
snarfMessage2 configuration items (see above). They use the following
substitution parameters:

    %a       Author name
    %b       Branch being watched ('unknown' in snarf messages).
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

Here is a format string template that I am partial to:

    commitMessage1 = %![%!%(14)%s%(15)%!|%!%(14)%b%(15)%!|%!%(14)%a%(15)%!]%! %m
    commitMessage2 = View%!:%! %(4)http://github.com/leamas/supybot-git/commits/%c

As noted above, the default is a simpler version of this:

    commitMessage1 = [%s|%b|%a] %m
    commitMessage2 = '' (unset)
    snarfMessage1  = I. e., [%s|%b|%a] %m
    snarfMessage2  = ''

Leading space in any message line is discarded. Prepend line with %S if you
want an indentation.


Command List
------------

* `repolog`: Takes a repository name, a branch  and an optional
  count parameter (default 1).  Shows the last n commits on that branch.
  Only works if the repository is configured for the current channel.

* `repolist`: List any known repositories configured for the current
  channel.

* `repostat`: Lists tracked branches for a given repository.

* `repoadd`: Adds a new repo given it's name, an url and one or more channels
  which should be connected. The url might be a relative path, interpreted from
  supybot's start directory.

* `repokill`: Remove an  existing repository given it's name.

* `repopoll`: Run a poll on a repository if given one, else poll all of them.

* `repoconf`: Display configuration for a repository.

* `gitconf`: Display overall, common configuraiton for all repositories.

* `reload Git`: Read new configuration, restart polling.

* `githelp` : Display url to help (i. e., this file).

How Notification Works
----------------------

When a repository is created it's also cloned. After this, a thread fetches
changes from the remote repo periodically.

**Warning #1:** If the repository is big and/or the network is slow, the
first clone (when creating repo) may take a very long time!

**Warning #2:** If the repositories you track are big, this plugin will use a
lot of disk space for its local clones.

After each fetch a  poll operation runs (generally pretty quick), including
a check for any commits that arrived since the last check.

Repository clones are deleted by @repokill. To recover from bad upstreams doing
push -f (or worse) try to run a @repokill + @repoadd cycle.


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
