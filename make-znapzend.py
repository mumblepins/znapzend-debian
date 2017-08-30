#!/usr/bin/env python

from __future__ import print_function

import os
import re
import shlex
import shutil
import sys
from Queue import Queue
from contextlib import contextmanager
from subprocess import check_output, Popen, PIPE
from threading import Thread

USER_EMAIL = os.environ['USER_EMAIL']
USER_NAME = os.environ['USER_NAME']
PPA = os.environ['PPA']

ZZ_URL = 'https://github.com/oetiker/znapzend.git'

build_dir = 'znapzend-build'

environment = dict(os.environ,
                   DEBEMAIL=USER_EMAIL,
                   DEBFULLNAME=USER_NAME,
                   DEB_BUILD_OPTIONS="nocheck"
                   )

RED = "\033[1;31m"
BLUE = "\033[1;34m"
CYAN = "\033[1;36m"
GREEN = "\033[0;32m"
RESET = "\033[0;0m"

current_branch = check_output(shlex.split('git rev-parse --abbrev-ref HEAD')).strip()
deploy = True if current_branch == 'master' else False


def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


@contextmanager
def cd(newdir):
    prevdir = os.getcwd()
    os.chdir(os.path.expanduser(newdir))
    try:
        yield prevdir, os.getcwd()
    finally:
        os.chdir(prevdir)


def reader(pipe, queue, name):
    try:
        with pipe:
            for line in iter(pipe.readline, b''):
                queue.put((pipe, line, name))
    finally:
        queue.put(None)


def run_command_iter(string, echo=True, quiet=False, dry_run=False, colored=True, *args, **kwargs):
    if 'shell' not in kwargs or not kwargs['shell']:
        cmd = shlex.split(string)
    else:
        cmd = string
    if echo:
        if dry_run:
            eprint("Dry run: {}".format(cmd))
        else:
            eprint("Running: {}".format(cmd))
    if dry_run:
        return
    process = Popen(cmd, stdout=PIPE, stderr=PIPE, *args, **kwargs)
    # print process.communicate()
    # sys.exit()
    q = Queue()
    Thread(target=reader, args=[process.stdout, q, 'stdout']).start()
    Thread(target=reader, args=[process.stderr, q, 'stderr']).start()
    for _ in range(2):
        for source, line, name in iter(q.get, None):
            if not quiet:
                if name == 'stdout':
                    yield 'stdout', line
                else:
                    if colored:
                        line = RED + line + RESET
                    yield 'stderr', line
                    # sys.stderr.write(RED)
                    # sys.stderr.write(line)
                    # sys.stderr.write(RESET)


def run_command(*args, **kwargs):
    for t, ln in run_command_iter(*args, **kwargs):
        if t == 'stdout':
            sys.stdout.write(ln)
        else:
            sys.stderr.write(ln)


def mkdirp(directory):
    d = os.path.abspath(directory)
    try:
        os.makedirs(d, 0o0700)
    except OSError as e:
        if e.errno == 17:  # Directory exists
            os.chown(d, os.getuid(), os.getgid())
            os.chmod(d, 0o0700)
        else:
            raise
    return d


def clean(directory):
    try:
        shutil.rmtree(directory)
    except OSError as e:
        if e.errno == 2:
            pass
        else:
            raise


def clone_and_checkout(url, branch=None, gitdir=None):
    if gitdir is None:
        gitdir = os.path.basename(url).replace('.git', '')
    run_command('git clone {} {}'.format(url, gitdir))
    if branch is not None:
        with cd(gitdir):
            run_command('git checkout {}'.format(branch))
    return gitdir


run_command('curl -SlL {} | gpg --import'.format(os.environ['SIGN_URI']), echo=False, quiet=True, shell=True)

clean(build_dir)
build_dir = mkdirp(build_dir)

with cd(build_dir) as (prevdir, curdir):
    zz_dir = clone_and_checkout(ZZ_URL)
    shutil.copytree(os.path.join(prevdir, 'debian'), os.path.join(zz_dir, 'debian'))
    zz_dir = os.path.abspath(zz_dir)

with cd(zz_dir):
    run_command('./configure')
    run_command('make')

    with open('thirdparty/Makefile.am', 'r') as mkfh:
        mkdata = mkfh.readlines()

    with open('thirdparty/Makefile.am', 'w') as mkfh:
        found_touch = False
        for line in mkdata:
            if found_touch:
                line = re.sub('^\t', '#\t', line)
            mkfh.write(line)
            if "POPULATING OUR" in line:
                found_touch = True

    os.remove('thirdparty/Makefile')
    run_command('automake')

    cmd = "debuild --no-tgz-check -S  -p'gpg --no-tty --passphrase {}'".format(os.environ['SIGN_PASSWORD'])
    for typ, line in run_command_iter(cmd, env=environment, shell=True, echo=False):
        if 'signfile' in line and '.changes' in line:
            sys.stdout.write(BLUE)
            chngfile = re.search(r'\s+(\S*\.changes)\s+', line).groups()[0]
        if typ == 'stderr':
            sys.stderr.write(line)
        else:
            sys.stdout.write(line)
        sys.stdout.write(RESET)

with cd(build_dir):
    if deploy:
        cmd = 'dput -u ppa:{ppaname} {chngfile}'.format(ppaname=PPA, chngfile=chngfile)
    else:
        cmd = 'dput -u -s ppa:{ppaname} {chngfile}'.format(ppaname=PPA, chngfile=chngfile)

    run_command(cmd, env=environment)

print(build_dir)
