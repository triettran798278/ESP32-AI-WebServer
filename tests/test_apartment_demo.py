import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'apartment_demo.sh'


class ApartmentDemoTest(unittest.TestCase):
    def test_loads_repo_key_and_prefers_exported_key(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scripts = root / 'scripts'
            scripts.mkdir()
            script = scripts / SCRIPT.name
            shutil.copyfile(SCRIPT, script)
            (root / '.env').write_text('THINGSBOARD_API_KEY=tb_file-key\n')

            curl = root / 'curl'
            curl.write_text(
                '#!/usr/bin/env bash\n'
                'IFS= read -r header\n'
                '[[ "$header" == "X-Authorization: ApiKey $EXPECTED_KEY" ]]\n'
            )
            curl.chmod(0o700)
            env = dict(os.environ, PATH=f'{root}:{os.environ["PATH"]}')
            env.pop('THINGSBOARD_API_KEY', None)
            for exported_key in (None, 'tb_exported-key'):
                with self.subTest(exported_key=exported_key):
                    if exported_key is not None:
                        env['THINGSBOARD_API_KEY'] = exported_key
                    env['EXPECTED_KEY'] = exported_key or 'tb_file-key'
                    result = subprocess.run(
                        ['bash', str(script), '1'], cwd=scripts, env=env,
                        capture_output=True, text=True,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout.count('Submitted '), 5)
