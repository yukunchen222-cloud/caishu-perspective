import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))


class ReleaseTests(unittest.TestCase):
    def test_zip_contains_committed_skill_but_not_untracked_credentials(self):
        from package_release import package_release
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / 'skill'
            root.mkdir()
            subprocess.run(['git', 'init', '-q', str(root)], check=True, capture_output=True)
            subprocess.run(['git', '-C', str(root), 'config', 'core.autocrlf', 'true'], check=True)
            (root / 'SKILL.md').write_text('测试技能\n', encoding='utf-8')
            subprocess.run(['git', '-C', str(root), 'add', 'SKILL.md'], check=True)
            subprocess.run(['git', '-C', str(root), '-c', 'user.name=Release Test',
                            '-c', 'user.email=release-test@example.invalid', 'commit', '-qm', 'test'], check=True)
            (root / 'auth.json').write_text('NOT_A_REAL_CREDENTIAL', encoding='utf-8')
            archive = Path(folder) / 'skill.zip'
            receipt = package_release(root, archive)
            self.assertEqual(receipt['file_count'], 1)
            self.assertEqual(len(receipt['sha256']), 64)
            with zipfile.ZipFile(archive) as z:
                files = [name for name in z.namelist() if not name.endswith('/')]
                self.assertEqual(files, ['caishu-perspective/SKILL.md'])
                self.assertEqual(z.read(files[0]).decode('utf-8'), '测试技能\n')
            before = archive.read_bytes()
            with self.assertRaises(ValueError):
                package_release(root, archive)
            self.assertEqual(before, archive.read_bytes())

    def test_dirty_tracked_content_cannot_be_packaged_as_verified_commit(self):
        from package_release import package_release
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / 'skill'
            root.mkdir()
            subprocess.run(['git', 'init', '-q', str(root)], check=True, capture_output=True)
            (root / 'SKILL.md').write_text('before', encoding='utf-8')
            subprocess.run(['git', '-C', str(root), 'add', 'SKILL.md'], check=True)
            subprocess.run(['git', '-C', str(root), '-c', 'user.name=Release Test',
                            '-c', 'user.email=release-test@example.invalid', 'commit', '-qm', 'test'], check=True)
            (root / 'SKILL.md').write_text('uncommitted', encoding='utf-8')
            target = Path(folder) / 'bad.zip'
            with self.assertRaises(ValueError):
                package_release(root, target)
            self.assertFalse(target.exists())


if __name__ == '__main__':
    unittest.main()
