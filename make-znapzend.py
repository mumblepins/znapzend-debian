#!/usr/bin/env python
import shlex
import tempfile
import re

from contextlib import contextmanager
import os
import shutil
from os.path import basename
from subprocess import check_output

USER_EMAIL = os.environ['USER_EMAIL']
USER_NAME = os.environ['USER_NAME']
PPA = os.environ['PPA']

ZZ_URL = 'https://github.com/oetiker/znapzend.git'

ZZD_URL = 'https://github.com/mumblepins/znapzend-debian.git'
ZZD_BRANCH = 'develop'

environment = dict(os.environ,
                   DEBEMAIL=USER_EMAIL,
                   DEBFULLNAME=USER_NAME,
                   DEB_BUILD_OPTIONS="nocheck"
                   )


@contextmanager
def cd(newdir):
    prevdir = os.getcwd()
    os.chdir(os.path.expanduser(newdir))
    try:
        yield
    finally:
        os.chdir(prevdir)


def clone_and_checkout(url, branch=None, gitdir=None):
    if gitdir is None:
        gitdir = os.path.basename(url).replace('.git', '')
    _cmd = shlex.split('git clone {} {}'.format(url, gitdir))

    print check_output(_cmd)
    if branch is not None:
        with cd(gitdir):
            _cmd = shlex.split('git checkout {}'.format(branch))
            print check_output(_cmd)
    return gitdir


tempdir = tempfile.mkdtemp()
with cd(tempdir):
    zz_dir = clone_and_checkout(ZZ_URL)
    zzd_dir = clone_and_checkout(ZZD_URL, ZZD_BRANCH)
    shutil.move(os.path.join(zzd_dir, 'debian'), zz_dir)
    shutil.rmtree(zzd_dir)
    zz_dir = os.path.abspath(zz_dir)

with cd(zz_dir):
    print check_output('./configure')
    print check_output('make')

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
    print check_output('automake')

    cmd = shlex.split("debuild -S")
    for line in check_output(cmd, env=environment).splitlines():
        if 'signfile' in line and '.changes' in line:
            chngfile = re.search(r'\s+(\S*\.changes)\s+', line).groups()[0]
        print line

with cd(tempdir):
    cmd = shlex.split('dput -u ppa:{ppaname} {chngfile}'.format(ppaname=PPA, chngfile=chngfile))
    print cmd

    print check_output(cmd, env=environment)

print tempdir
