#!/usr/bin/env python

# This file should be available from
# http://www.pobox.com/~asl2/software/Pinefs
# and is licensed under the X Consortium license:
# Copyright (c) 2003, Aaron S. Lav, asl2@pobox.com
# All rights reserved.

# Permission is hereby granted, free of charge, to any person obtaining a
# copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, and/or sell copies of the Software, and to permit persons
# to whom the Software is furnished to do so, provided that the above
# copyright notice(s) and this permission notice appear in all copies of
# the Software and that both the above copyright notice(s) and this
# permission notice appear in supporting documentation.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
# OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT
# OF THIRD PARTY RIGHTS. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR
# HOLDERS INCLUDED IN THIS NOTICE BE LIABLE FOR ANY CLAIM, OR ANY SPECIAL
# INDIRECT OR CONSEQUENTIAL DAMAGES, OR ANY DAMAGES WHATSOEVER RESULTING
# FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT,
# NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION
# WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.

# Except as contained in this notice, the name of a copyright holder
# shall not be used in advertising or otherwise to promote the sale, use
# or other dealings in this Software without prior written authorization
# of the copyright holder.


"""Pyfs provides a view of Python namespace (rooted at sys.modules) as
a NFS filesystem.  The implementation is imperfect, because I can't
think of anything in Python which can be used for the 'fileid'
attribute or the filehandle, independent of either the contents of the
object or its place in the filesystem.  The compromise is to use a
cache (FileSystem._objs) to make sure that the same python directory
obj (defined as either an instance of a subclass of dict or dictproxy,
or an object which has a '__dict__' attribute) is always wrapped by
the same FileObj.  All other objects (e.g. Python integers, strings)
are wrapped by a new FileObj (with a new fileid) for each different
access path through the Python namespace.

In order to handle writing to immutable types (such as strings and
integers), each FileObj contains the parent dictionary and key through
which it was first encountered, and writing to regular files is
implemented by creating a new object and binding it as the new value
for that key in the parent dictionary.  (For writing to directories,
the dictionary is mutated in place.)  The new object's value is obtained
by stringifying the value (with str()), creating a new string by
replacing the indicated part of the old string, and then passing the
new string to type(val).  If the type object (e.g.  for functions)
doesn't accept a string as parameter, we report NFSERR_ACCES.  (Yes,
this is a bunch of overhead.)

For directories, instead of just using the __dict__, we probably
should track the logic used in 'dir' (or just call 'dir'), while being
aware that accesses to attributes returned from dir can raise
AttributeError (e.g. __slots__).  Currently, we don't implement access
to the __class__ attribute of class instances, attributes defined with
__slots__ (or other attributes defined by means of attribute
descriptors), or to dynamically-generated attributes generated by
manipulating __getattr__/__getattribute__.  (The general problem seems
insoluble, at least without an assist from the __members__ attribute.)

Note that hard links to non-directories don't work with this system.
(A hard link request is currently implemented as a copy.)  To fix this, a
FileObj could have a list of (parent_dict, key) tuples, and a write
would iterate over the list and rebind each parent_dict[key].

XXX This code isn't safe if the Python side mutates directories
exactly when the NFS code is reading them.  When it's rewritten to be
safe, test by pausing NFS code at important points (e.g. inside
refresh_dir), waiting for the user to mutate stuff at the python
console, and then signal to continue from console.

Here's a useless example (except for testing purposes):
find  .  -name __doc__ -noleaf  -exec grep "maxint" \{\} /dev/null \;
(executed in root of NFS mount)

Note that there are many paths through the Python namespace to the
module sys, which currently has the only docstring with maxint in it
(unless this module is imported), and that find prints all of them.
(pyfs returns the same filehandle and fileid each time, so it is
possible to realize they're all duplicates.)
"""


import sys
import string

import rfc1094
import fsbase
import types

trace_fh = 0


def get_dict(obj):
    if isinstance(obj, types.DictType) or isinstance(obj, types.DictProxyType):
        return obj
    return getattr(obj, '__dict__', None)
# sometimes obj has a __dict__ attribute which is None.  This
# still does what we want.


class FileObj(fsbase.FileObj):
    fileid_ctr = fsbase.Ctr(randomize_start=1)
    # can't g'tee persistence of file ids, 2nd best is to
    # randomize them so previous incarnations will get ESTALE

    def __init__(self, parent_dict, key, fs):
        self.fs = fs

        self.parent_dict = parent_dict
        self.key = key

        self.fileid = self.fileid_ctr.next()
        obj = self.parent_dict[self.key]

        dict = get_dict(obj)
        if dict <> None:
            self.set_dict(dict)
        else:
            self.type = rfc1094.NFREG
            self.data = self.get_data()

        nlink = self.get_nlink()
        # XXX ideally this would be property, but interacts poorly w/
        # getattr in fsbase
        fsbase.FileObj.__init__(self)

    def get_nlink(self):
        if self.type == rfc1094.NFDIR:
            return sys.getrefcount(self.parent_dict[self.key])
        else:
            return 1

    def set_dict(self, dict_obj):
        self.type = rfc1094.NFDIR
        self.dict = dict_obj
        self.size = len(dict_obj)
        self.dir = {}
        self.blocks = 1

    def get_data(self):
        try:
            return str(self.parent_dict[self.key])
        except KeyError, k:
            print "weird, key %s missing from %s" % (str(self.key),
                                                     str(self.parent_dict.keys()))
            return ''

    def read(self, offset, count):
        self.data = self.get_data()
        return self.data[offset: offset + count]

    def write(self, offset, newdata):
        old_data = self.get_data()
        old_len = len(old_data)
        if offset > old_len:
            fill = '\0' * (offset - old_len)
        else:
            fill = ''
        new_data = (old_data[:offset] + fill + newdata +
                    old_data[offset + len(newdata):])
        self.change_val(new_data)

    def change_val(self, *args):
        try:
            new_val = type(self.parent_dict[self.key])(*args)
        except (TypeError, ValueError):
            raise fsbase.NFSError(rfc1094.NFSERR_ACCES)
        self.parent_dict[self.key] = new_val
        self.data = self.get_data()
        self.set_size()
        # This is "rebind", not "mutate".
        self.mtime = fsbase.mk_now()

    def truncate(self):
        """Note that for non-strings, 0-len data is usually invalid, so we
        interpret 'truncate' liberally"""
        self.change_val()

    def check_changed(self):
        """Called on every access.  Stringifies data, and compares it
        with old value to see if it's changed (so that when the python
        side changes a value, we reflect that with a changed mtime in
        GETATTR, and the NFS client can reread if necesary.This is
        comparatively heavyweight, and maybe there should be a flag to
        turn it off."""
        if self.type <> rfc1094.NFDIR:
            new_data = self.get_data()
            if new_data <> self.data:
                self.mtime = fsbase.mk_now()
                self.data = new_data
                self.set_size()

# __{get,set,del}item__ are implemented to ease manipulating both self.dict
# (the dict of the python object, with python objects as vals) and self.dir,
# which contains NFS file handles for those objects, at the same time,
# and keeping them consistent.  They take and return tuples of (fh, obj)
    def __getitem__(self, key):
        return self.dir[key], self.dict[key]

    def __setitem__(self, key, val):
        fh, obj = val
        self.dict[key] = obj
        self.dir[key] = fh

    def __delitem__(self, key):
        del self.dict[key]  # try dict first!
        del self.dir[key]

    def set_dir(self, key, fh):
        if fh <> None:
            self.dir[key] = fh
        else:
            del self.dir[key]

    def get_dir(self):
        # It would be nice if there were a cheap way to tell if
        # self.dict had changed at all, rather than just checking for
        # length changes.  So we miss some alterations.  I guess we
        # could have a timestamp, so we refresh the directory when the
        # length changes, or every n seconds.  Alternately, we could
        # just save old_dict and compare .items (), since we're doing
        # the moral equivalent for files.

        if self.dir == None or len(self.dir) <> len(self.dict):
            self.refresh_dir()
        return self.dir

    def refresh_dir(self):
        # exclude _fils, _objs to avoid apps traversing entire directory tree
        # from looping forever

        if (self.dict <> self.fs._fils and
                self.dict <> self.fs._objs):
            old_dir = self.dir
            self.dir = {}

# Avoid names with '/' because my Linux 2.4.19 seems to get slightly
# confused with them.  (E.g. a name of '/' by itself is a link to the
# root of the directory hierarchy, even if it's a Python string and
# thus ought to be a leaf.)  Ideally I'd escape them, so they were
# still accessible somehow.
# XXX Avoiding '/'s means len's won't match, we'll refresh every time through

            for (k, v) in self.dict.items():
                if isinstance(k, type('')):
                    if k.find('/') <> -1:
                        continue
                fh = old_dir.get(k, None)
                if fh == None:
                    fh = self.fs.find_or_create(self.dict, k)
                else:
                    del old_dir[k]
                self.dir[str(k)] = fh
# XXX old_dir now contains filehandles that there may be no other way
# to reach (certainly if they refer to non-directories).
# On one hand, to provide Unix semantics, if the client still
# has that filehandle, it can refer to it forever:
# on the other, it's a memory leak (from fs._fils and fs._objs)
# if it does.  Note that the only way this can arise is to
# delete things from the python side, since any manipulation
# through the NFS side maintains dict and dir in sync (unless it's buggy).
# Maybe the way to resolve this is to keep a link count for directory-like
# objects (since we can rely on identity for them), purging when the link
# count reaches 0: for others, put the filehandles in a dictionary
# of fh's to be purged, and
# - keep them in, er, purgatory (resetting the last access time) if they're
#   used by a client through an old file handle
# - otherwise delete them after a decent interval

    def mk_link(self, name, from_fh):
        from_fil = self.fs.get_fil(from_fh)
        self.dict[name] = from_fil.parent_dict[from_fil.key]
        self.set_dir(name, from_fh)


class FileSystem:
    def __init__(self):
        self._fh_ctr = fsbase.Ctr(randomize_start=1)
        self._fils = {}  # map fh to FileObj
        self._objs = {}  # map id to (obj, fh)
        self._root = self.find_or_create(sys.__dict__, 'modules')

    def mount(self, dirpath):
        if dirpath == '/':
            return self._root
        return None

    def find_or_create(self, dict, key):
        py_obj = dict[key]
        d = get_dict(py_obj)
        if d <> None:
            tup = self._objs.get(id(py_obj))
        else:
            tup = None
        if tup == None:
            fh = self._fh_ctr.next_fh()
            fattr = FileObj(dict, key, self)
            if trace_fh:
                print "creating fh %s key %s" % (fh, str(key))
            self._fils[fh] = fattr
            if d <> None:
                self._objs[id(py_obj)] = (py_obj, fh)
            return fh
        else:
            # XXX tup [0] should be weak ref, but until then, we're
            # certain that tup [0] == py_obj
            assert (tup[0] == py_obj)
            fh = tup[1]
        return fh

    def get_fil(self, fh):
        f = self._fils.get(fh, None)
        if f <> None:
            f.check_changed()
            f.atime = fsbase.mk_now()
        return f

    def rename(self, old_dir, old_name, new_dir, new_name):
        #        print "rename", old_name, new_name
        old_fil = self.get_fil(old_dir)
        new_fil = self.get_fil(new_dir)
        move_fh = old_fil.get_dir()[old_name]
        move_fil = self.get_fil(move_fh)
        new_fil[new_name] = (move_fh, move_fil.parent_dict[move_fil.key])
        move_fil.key = new_name
        del old_fil[old_name]

    def create_fil(self, dir_fh, name, **kw):
        dir_fil = self.get_fil(dir_fh)
        if kw['type'] == rfc1094.NFDIR:
            new_val = {}
        else:
            new_val = kw.get('data', '')
        dir_fil.refresh_dir()
        dir_fil.dict[name] = new_val
        fh = self.find_or_create(dir_fil.dict, name)
        dir_fil.set_dir(name, fh)
        return fh, self.get_fil(fh)

    def remove(self, dir_fh, name):
        dir_fil = self.get_fil(dir_fh)
        try:
            old_fh = dir_fil.get_dir()[name]
            old_fil = self.get_fil(old_fh)
            py_obj = old_fil.parent_dict[old_fil.key]
            if old_fil.type == rfc1094.NFDIR:
                if old_fil.dict <> {}:
                    raise fsbase.NFSError(rfc1094.NFSERR_NOTEMPTY)
            del dir_fil[name]
        except TypeError:
            # NFSERR_ACCES isn't quite right, because it implies
            # that some user could delete this.
            raise fsbase.NFSError(rfc1094.NFSERR_ACCES)
        except KeyError:
            raise fsbase.NFSError(rfc1094.NFSERR_NOENT)

        del self._fils[old_fh]

        d = get_dict(py_obj)
        if d <> None:
            del self._objs[id(py_obj)]
