"""Run the Python suite with external HTTP disabled, including child processes."""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUARD = '''import urllib.request, os, traceback
def offline_request(*args, **kwargs):
    with open(os.environ["FRONTIER_OFFLINE_HTTP_LOG"], "a") as audit:
        audit.write("".join(traceback.format_stack(limit=6)))
    raise AssertionError("Offline regression attempted unmocked HTTP")
urllib.request.urlopen = offline_request
'''


def main():
    with tempfile.TemporaryDirectory(prefix='frontier-offline-') as directory:
        Path(directory,'sitecustomize.py').write_text(GUARD)
        audit=Path(directory,'http-attempts.log')
        env = {**os.environ, 'PYTHONPATH':directory + os.pathsep + os.environ.get('PYTHONPATH',''),
               'FRONTIER_OFFLINE_HTTP_LOG':str(audit)}
        for key in ['AI_PROVIDER','OPENAI_API_KEY','DEEPSEEK_API_KEY','OPENAI_MODEL','DEEPSEEK_MODEL']:
            env.pop(key,None)
        result = subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-p',
                                 sys.argv[1] if len(sys.argv)>1 else 'test_*.py'],cwd=ROOT,env=env)
        if audit.exists():
            print('Unmocked external HTTP was blocked:\n'+audit.read_text()[:4000])
            return 1
        return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())
