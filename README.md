### Introduction

Pinefs is a user-space NFS server, written entirely in Python. It
provides three sample filesystems: pyfs, which provides a view of the
entire Python namespace as a file system, allowing you to change
variables in a running Python program by writing to the corresponding
file, or to use Unix tools like find; memfs, a fairly trivial in-memory
filesystem; and tarfs, which populates memfs from a tar file specified
by the mount command (requires tarfile, included in Python 2.3, or
[available separately](http://www.gustaebel.de/lars/tarfile/)). The
package also includes rpcgen.py, a Python compiler from ONC RPC IDL to
Python source. Pinefs requires Python 2.2 or later, and has been
developed on Linux and lightly tested on Win 98. You can download it
[here](Pinefs-1.1.tar.gz).

### Running the Pinefs pyfs Server

srv.py takes a single option, \'-f\', which defaults to \'py\' for the
Python filesystem, but can be \'mem\' for the memory filesystem or
\'tar\' for the tar filesystem. When the Python filesystem is specified,
the server runs a Python interactive loop.

The mount server runs on port 5555, and the NFS server on 2049. (Both
register with the portmapper.) On my Linux box, I use the following
command to mount the server for pyfs:

    mount -t nfs -o noac 127.0.0.1:/ /mnt/nfs

Once the Python filesystem is mounted, you can try:

    echo 1 > <mount point>/rpchelp/trace_rpc

to set the global trace\_rpc in module rpchelp to 1, which causes
information about rpc calls to be printed. You should see trace
information for the NFSPROC\_WRITE call. After you\'ve looked around the
filesystem for a bit, you can turn off tracing by either:

    echo 0 > <mount point>/rpchelp/trace_rpc

or typing into the Python interaction loop:

    import rpchelp
    rpchelp.trace_rpc = 0

See [here](pyfs.html) for more information on the mapping implemented by
pyfs. The mapping isn\'t perfect, but works well enough to use emacs, or
to untar, configure, and compile, e.g., my [Dissociated
Studio](http://www.pobox.com/~asl2/music/dissoc_studio/) package. (Note:
if you want a production-quality monitoring/debugging system, you should
probably use something built for that purpose (like manhole from
[Twisted](http://www.twistedmatrix.com/)), since you could get more
functionality, Pinefs doesn\'t address synchronization issues, and pyfs
filehandles aren\'t persistent across restarts).)

### Running the Pinefs tarfs Server

This works much as above, except that instead of 127.0.0.1:/, substitute
for / the pathname to a tar file. Now you can, change directory to the
mount point and browse, or, if it\'s a software package, e.g.,
./configure; make.

### Running rpcgen.py

rpcgen.py takes an IDL filename as a parameter, and writes Python code
implementing that IDL on stdout. The generated code imports rpchelp and
rpc from the Pinefs distribution, which thus must be present at runtime.
rpcgen.py requires Dave Beazley\'s [PLY
package](http://systems.cs.uchicago.edu/ply/), licensed under the LGPL.
Pinefs includes a precompiled rfc1094.py (generated from rfc1094.idl),
so you don\'t need PLY in order to run Pinefs. See [here](rpcgen.html)
for more information on rpcgen.

### Notes

There are several other related programs, of which I was unaware, partly
because they weren\'t in [PyPI](http://www.python.org/pypi) orthe
[Vaults of Parnassus](http://www.vex.net/parnassus), partly because they
weren\'t in the first ten pages or so of google results (web and
comp.lang.python.\* search) when I initially looked, and partly because
I started from the Python 2.1 rather than 2.2 Demo/rpc directory.
(Consider this a plea for people to use Vaults or post to
comp.lang.python.announce.) I still think Pinefs may be of interest,
because it exposes the Python namespace via NFS, and the included rpcgen
handles nested structs and unions.

Here are the others:

-   [Pynfs](http://www.cendio.se/~peter/pynfs/), a NFSv4 client, server,
    and test suite, and rpcgen
-   [Zodbex
    NFS](http://cvs.sourceforge.net/cgi-bin/viewcvs.cgi/zodbex/zodbex/nfs/),
    a NFSv\[23\] implementation with an in-memory filesystem
-   Wim Lewis\'s
    [rpcgen.py](http://www.omnigroup.com/~wiml/soft/stale-index.html#python)

Pinefs is licensed under a MIT/X style license, except for rpc.py,
which, since my version is based on the Python 2.1 distribution, has the
Python license.

The name \"Pinefs\" is both a pun on PyNFS, the obvious name for such a
program, and allows me to make the quasi-obligatory
[allusion](http://www.mtholyoke.edu/~ebarnes/python/dead-parrot.htm) :
\"It\'s pining for the files!\"

If you have any questions, you can reach me at [Aaron
Lav](mailto:asl2@pobox.com).

[Back](http://www.pobox.com/~asl2/) to Aaron\'s home page.

### pyfs

    Pyfs provides a view of Python namespace (rooted at sys.modules) as
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

[Back to Pinefs home page](README.html)

### rpcgen

    Parser for ONC RPC IDL.  The grammar is taken from RFC1832, sections
    5, and RFC1831, section 11.2.

    The output Python code (which requires rpchelp and rpc from the Pinefs
    distribution) contains a separate class (with rpchelp.Server as a base
    class) for every version defined in every program statement.  To
    implement a service, for each version of each program, derive a class
    from the class named <prog>_<version>, with method names corresponding
    to the procedure names in the IDL you want to implement.  (At
    instantiation, any procedure names defined in the IDL but neither
    implemented nor listed in the deliberately_unimplemented member will
    cause a warning to be printed.)  Also, define a member function
    check_host_ok, which is passed (host name, credentials, verifier) on each
    call, and should return a true value if the call should be accepted,
    and false otherwise.

    To use instances of the server class, create a transport server (with
    the create_transport_server(port) function), and then, for every server
    instance you want associated with that port, call its
    register(transport_server) function, which will register with the
    local portmapper.  (This architecture allows multiple versions of
    multiple programs all to listen on the same port, or for a single version
    to listen on, e.g, both a TCP and UDP port.)

    Member functions will be passed Python values, and should return
    a Python value.  The correspondence between IDL datatypes and
    Python datatypes is:
    - base types uint, int, float, double are the same
    - void is None
    - an array (either fixed or var-length) is a Python sequence
    - an opaque or a string is a Python string
    - a structure is a Python instance, with IDL member names corresponding
      to Python attribute names
    - a union is a two-attribute instance, with one attribute named the
      name of the discriminant declaration, and the other named '_data'
      (with a value appropriate to the value of the discriminant).
    - an optional value (*) is either None, or the value
    - a linked list is special-cased, and turned into a Python list
      of structures without the link member.
    - const and enum declarations are top-level constant variables.

    IDL identifiers which are Python reserved words (or Python reserved
    words with 1 or more underscores suffixed) are escaped by appending
    an underscore.

    Top-level struct and union declarations generate Python declarations
    of the corresponding name, and calling the object bound to the name
    will generate an instance suitable for populating.  (The class defines
    __slots__ to be the member names, and has, as attributes, any nested
    struct or union definitions.  The packing/unpacking function don't
    require the use of this class, and, for the unnamed struct/union
    declarations created by declaring struct or union types as either
    return values or argument types in a procedure definition, you'll need
    to create your own classes, either by using
    rpchelp.struct_union_class_factory, or some other way.)

    Enum declarations nested inside struct or union declarations, or
    procedure definitions, generate top-level definitions.  (I think this
    treatment of nested enum definitions is wrong, according to RFC1832
    section 5.4, but I'm not sure.)

    Rpcgen doesn't support:
    - 'unsigned' as a synonym for 'unsigned int'
    - case fall-through in unions
    Neither seems to be defined in the grammar, but I should support them,
    and look around for an updated IDL specification.

[Back to Pinefs home page](README.html)
