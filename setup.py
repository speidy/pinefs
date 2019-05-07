#!/usr/bin/env python

from distutils.core import setup

import vers

setup(name="pinefs",
      version=vers.version,
      packages=['pinefs', ],
      license="X",
      author="Aaron Lav",
      author_email="asl2@pobox.com",
      description='Python NFS server and ONC RPC compiler',
      long_description="""Python implementation of NFS v2 server,
       implementing a simple in-memory filesysPtem, a filesystem view
       of the Python namespace, and a tar filesystem.  Includes rpcgen,
       an IDL compiler.""",
      platforms="Any Python 2.2 or later",
      url="http://www.pobox.com/~asl2/software/Pinefs",
      entry_points={
              'console_scripts': [
                  'pinefs-server=pinefs.srv:main',
              ],
      })
