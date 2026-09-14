"""Validate the real bundled interpreter and native UTF-8 filesystem behavior."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'artifacts'))
from windows.build import configure_python_utf8, prune_python_templates, native_images


@unittest.skipUnless(os.name=='nt','requires native Windows')
class WindowsPythonPayload(unittest.TestCase):
    def test_relocated_python_and_native_utf8_filenames(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)/"中文 user's Python"
            python=root/'python'
            shutil.copytree(Path(sys.base_prefix),python)
            prune_python_templates(python)
            configure_python_utf8(python,root/'manifests')
            self.assertTrue(native_images(python))
            probe=r'''
import ctypes,json,sys
from pathlib import Path
root=Path(sys.argv[1])
assert Path(sys.base_prefix).resolve()==(root/'python').resolve()
assert ctypes.windll.kernel32.GetACP()==65001
path=root/'中文 native file.txt'
path.write_text('example',encoding='utf-8')
crt=ctypes.CDLL('ucrtbase',use_errno=True)
crt.fopen.argtypes=[ctypes.c_char_p,ctypes.c_char_p]; crt.fopen.restype=ctypes.c_void_p
crt.fgetc.argtypes=[ctypes.c_void_p];crt.fgetc.restype=ctypes.c_int
crt.fclose.argtypes=[ctypes.c_void_p];crt.fclose.restype=ctypes.c_int
file=crt.fopen(str(path).encode('utf-8'),b'rb')
assert file,ctypes.get_errno()
try: assert crt.fgetc(file)==ord('e')
finally: crt.fclose(file)
print(json.dumps({'base_prefix':sys.base_prefix,'native_utf8_file':True}))
'''
            env=dict(os.environ,PATH=os.pathsep.join([str(python),os.environ['SystemRoot']+'/System32',os.environ['SystemRoot']]))
            result=subprocess.check_output([str(python/'python.exe'),'-I','-B','-c',probe,str(root)],env=env)
            self.assertTrue(json.loads(result)['native_utf8_file'])


if __name__=='__main__':
    unittest.main(verbosity=2)
