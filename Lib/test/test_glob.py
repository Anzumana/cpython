import unittest
from test.support import (run_unittest, TESTFN, skip_unless_symlink,
    can_symlink, create_empty_file)
import glob
import os
import shutil
import sys


class GlobTests(unittest.TestCase):

    def norm(self, *parts):
        return os.path.normpath(os.path.join(self.tempdir, *parts))

    def mktemp(self, *parts):
        filename = self.norm(*parts)
        base, file = os.path.split(filename)
        if not os.path.exists(base):
            os.makedirs(base)
        create_empty_file(filename)

    def setUp(self):
        self.tempdir = TESTFN + "_dir"
        self.mktemp('a', 'D')
        self.mktemp('aab', 'F')
        self.mktemp('.aa', 'G')
        self.mktemp('.bb', 'H')
        self.mktemp('aaa', 'zzzF')
        self.mktemp('ZZZ')
        self.mktemp('a', 'bcd', 'EF')
        self.mktemp('a', 'bcd', 'efg', 'ha')
        if can_symlink():
            os.symlink(self.norm('broken'), self.norm('sym1'))
            os.symlink(self.norm('broken'), self.norm('sym2'))

    def tearDown(self):
        shutil.rmtree(self.tempdir)

    def glob(self, *parts):
        if len(parts) == 1:
            pattern = parts[0]
        else:
            pattern = os.path.join(*parts)
        p = os.path.join(self.tempdir, pattern)
        res = glob.glob(p)
        self.assertEqual(list(glob.iglob(p)), res)
        return res

    def assertSequencesEqual_noorder(self, l1, l2):
        self.assertEqual(set(l1), set(l2))

    def test_glob_literal(self):
        eq = self.assertSequencesEqual_noorder
        eq(self.glob('a'), [self.norm('a')])
        eq(self.glob('a', 'D'), [self.norm('a', 'D')])
        eq(self.glob('aab'), [self.norm('aab')])
        eq(self.glob('zymurgy'), [])

        # test return types are unicode, but only if os.listdir
        # returns unicode filenames
        uniset = set([str])
        tmp = os.listdir('.')
        if set(type(x) for x in tmp) == uniset:
            u1 = glob.glob('*')
            u2 = glob.glob('./*')
            self.assertEqual(set(type(r) for r in u1), uniset)
            self.assertEqual(set(type(r) for r in u2), uniset)

    def test_glob_one_directory(self):
        eq = self.assertSequencesEqual_noorder
        eq(self.glob('a*'), map(self.norm, ['a', 'aab', 'aaa']))
        eq(self.glob('*a'), map(self.norm, ['a', 'aaa']))
        eq(self.glob('.*'), map(self.norm, ['.aa', '.bb']))
        eq(self.glob('?aa'), map(self.norm, ['aaa']))
        eq(self.glob('aa?'), map(self.norm, ['aaa', 'aab']))
        eq(self.glob('aa[ab]'), map(self.norm, ['aaa', 'aab']))
        eq(self.glob('*q'), [])

    def test_glob_nested_directory(self):
        eq = self.assertSequencesEqual_noorder
        if os.path.normcase("abCD") == "abCD":
            # case-sensitive filesystem
            eq(self.glob('a', 'bcd', 'E*'), [self.norm('a', 'bcd', 'EF')])
        else:
            # case insensitive filesystem
            eq(self.glob('a', 'bcd', 'E*'), [self.norm('a', 'bcd', 'EF'),
                                             self.norm('a', 'bcd', 'efg')])
        eq(self.glob('a', 'bcd', '*g'), [self.norm('a', 'bcd', 'efg')])

    def test_glob_directory_names(self):
        eq = self.assertSequencesEqual_noorder
        eq(self.glob('*', 'D'), [self.norm('a', 'D')])
        eq(self.glob('*', '*a'), [])
        eq(self.glob('a', '*', '*', '*a'),
           [self.norm('a', 'bcd', 'efg', 'ha')])
        eq(self.glob('?a?', '*F'), map(self.norm, [os.path.join('aaa', 'zzzF'),
                                                   os.path.join('aab', 'F')]))

    def test_glob_directory_with_trailing_slash(self):
        # Patterns ending with a slash shouldn't match non-dirs
        res = glob.glob(os.path.join(self.tempdir, 'Z*Z') + os.sep)
        self.assertEqual(res, [])
        res = glob.glob(os.path.join(self.tempdir, 'ZZZ') + os.sep)
        self.assertEqual(res, [])
        # When there is wildcard pattern which ends with os.sep, glob()
        # doesn't blow up.
        res = glob.glob(os.path.join(self.tempdir, 'aa*') + os.sep)
        self.assertEqual(len(res), 2)
        # either of these results are reasonable
        self.assertIn(set(res), [
                      {self.norm('aaa'), self.norm('aab')},
                      {self.norm('aaa') + os.sep, self.norm('aab') + os.sep},
                      ])

    def test_glob_bytes_directory_with_trailing_slash(self):
        # Same as test_glob_directory_with_trailing_slash, but with a
        # bytes argument.
        res = glob.glob(os.fsencode(os.path.join(self.tempdir, 'Z*Z') + os.sep))
        self.assertEqual(res, [])
        res = glob.glob(os.fsencode(os.path.join(self.tempdir, 'ZZZ') + os.sep))
        self.assertEqual(res, [])
        res = glob.glob(os.fsencode(os.path.join(self.tempdir, 'aa*') + os.sep))
        self.assertEqual(len(res), 2)
        # either of these results are reasonable
        self.assertIn({os.fsdecode(x) for x in res}, [
                      {self.norm('aaa'), self.norm('aab')},
                      {self.norm('aaa') + os.sep, self.norm('aab') + os.sep},
                      ])

    @skip_unless_symlink
    def test_glob_broken_symlinks(self):
        eq = self.assertSequencesEqual_noorder
        eq(self.glob('sym*'), [self.norm('sym1'), self.norm('sym2')])
        eq(self.glob('sym1'), [self.norm('sym1')])
        eq(self.glob('sym2'), [self.norm('sym2')])

    @unittest.skipUnless(sys.platform == "win32", "Win32 specific test")
    def test_glob_magic_in_drive(self):
        eq = self.assertSequencesEqual_noorder
        eq(glob.glob('*:'), [])
        eq(glob.glob(b'*:'), [])
        eq(glob.glob('?:'), [])
        eq(glob.glob(b'?:'), [])
        eq(glob.glob('\\\\?\\c:\\'), ['\\\\?\\c:\\'])
        eq(glob.glob(b'\\\\?\\c:\\'), [b'\\\\?\\c:\\'])
        eq(glob.glob('\\\\*\\*\\'), [])
        eq(glob.glob(b'\\\\*\\*\\'), [])


def test_main():
    run_unittest(GlobTests)


if __name__ == "__main__":
    test_main()
