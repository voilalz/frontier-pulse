#!/usr/bin/env python3
"""Accept only successful trusted main publications for workflow handoff."""
import json
import os
from pathlib import Path

TRUSTED = {'Daily classic papers', 'Daily news update', 'Full stream update', 'Restore retained release',
           'Deepread recovery'}


def allowed(name, event, repository, ref):
    if ref != 'refs/heads/main':
        return False
    if name in {'push', 'workflow_dispatch'}:
        return True
    if name != 'workflow_run':
        return False
    run = event.get('workflow_run') or {}
    return (run.get('name') in TRUSTED and run.get('conclusion') == 'success'
            and run.get('head_branch') == 'main'
            and (run.get('head_repository') or {}).get('full_name') == repository)


def main():
    event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text(encoding='utf-8'))
    deploy = allowed(os.environ.get('GITHUB_EVENT_NAME'), event,
                     os.environ.get('GITHUB_REPOSITORY'), os.environ.get('GITHUB_REF'))
    with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as output:
        output.write('deploy=' + str(deploy).lower() + '\n')


if __name__ == '__main__':
    main()
