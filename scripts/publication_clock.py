"""Beijing formal edition target and delay deadline."""
import argparse
import math
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


def publication_timing(edition, now=None):
    now = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo('Asia/Shanghai'))
    target = datetime.fromisoformat(edition + 'T08:00:00').replace(tzinfo=ZoneInfo('Asia/Shanghai'))
    deadline = target.replace(minute=15)
    return {'targetPublishedAt':target.isoformat(), 'publicationDeadlineAt':deadline.isoformat(),
            'waitSeconds':max(0, math.ceil((target-now).total_seconds())), 'delayed':now > deadline,
            'delayMinutes':max(0, int((now-target).total_seconds() // 60))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--edition', required=True)
    parser.add_argument('--wait', action='store_true')
    args = parser.parse_args()
    timing = publication_timing(args.edition)
    if args.wait:
        if datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat() != args.edition or timing['waitSeconds'] > 1800:
            raise ValueError('Formal publication wait requires today and at most 30 minutes')
        while timing['waitSeconds']:
            time.sleep(min(30, timing['waitSeconds']))
            timing = publication_timing(args.edition)
    print(timing)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
