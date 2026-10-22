"""Простой HTTP-клиент регистрации для account_service.py.

Пример:
  python tools/register_client.py --name alice --nickname Alice
  python tools/register_client.py --list
  python tools/register_client.py --show alice
"""
import argparse
import json
import sys
from urllib import error, request


def call(server, method, path, payload=None):
    data = None
    headers = {'Accept': 'application/json'}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        headers['Content-Type'] = 'application/json; charset=utf-8'
    req = request.Request(server.rstrip('/') + path, data=data, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=10) as response:
            return response.status, json.loads(response.read().decode('utf-8'))
    except error.HTTPError as exc:
        raw = exc.read().decode('utf-8', errors='replace')
        try:
            value = json.loads(raw)
        except ValueError:
            value = {'error': 'http', 'message': raw}
        return exc.code, value
    except error.URLError as exc:
        return 0, {'error': 'connection', 'message': str(exc.reason)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--server', default='http://127.0.0.1:8099')
    parser.add_argument('--name', help='Имя нового пользователя')
    parser.add_argument('--nickname', help='Публичный ник')
    parser.add_argument('--uid', help='Необязательный UID (0xhex/decimal)')
    parser.add_argument('--list', action='store_true')
    parser.add_argument('--show', metavar='NAME')
    parser.add_argument('--delete', metavar='NAME')
    args = parser.parse_args(argv)

    if args.list:
        status, value = call(args.server, 'GET', '/accounts')
    elif args.show:
        status, value = call(args.server, 'GET', '/accounts/' + args.show)
    elif args.delete:
        status, value = call(args.server, 'DELETE', '/accounts/' + args.delete)
    elif args.name:
        payload = {'name': args.name}
        if args.nickname:
            payload['nickname'] = args.nickname
        if args.uid:
            payload['actor_uid'] = args.uid
        status, value = call(args.server, 'POST', '/register', payload)
    else:
        parser.error('Укажите --name (регистрация), --list, --show NAME или --delete NAME')

    print(json.dumps(value, ensure_ascii=False, indent=2))
    if status in (200, 201):
        return 0
    print(f'HTTP {status}', file=sys.stderr)
    return 1


if __name__ == '__main__':
    sys.exit(main())
