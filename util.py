from django.core.cache import cache
from assessment.models import Query, Document
from functools import wraps

def my_cache(func, timeout_secs = 30):
  '''A decorator for caching of function output.  Only works with zero
  argument object methods.'''
  @wraps(func)
  def cached_func(self):
    key = '%s %s cache' % (str(self), str(func))
    if cache.has_key(key):
      return cache.get(key)
    else:
      result = func(self)
      cache.set(key, result, timeout_secs)
      return result
  return cached_func

def parse_queries_file(file, message_callback = None):
  '''A generator over (unsaved) Query objects.  Expect lines to be in the
  the format <qid>:<query text>'''
  for line in file:
    splits = line.strip().split(':')
    if len(splits) != 2:
      continue
    yield Query(qid = splits[0], text = splits[1])

def parse_docscores_file(file, message_callback = None):
  '''A generator over (unsaved) QueryDocumentPair objects.  Expect lines to
  be in the format: <qid>:<doc>:<score>'''
  missing_queries = set()
  for line in file:
    splits = line.strip().split(':')
    if len(splits) != 3:
      continue
    (qid, doc, score) = splits
    if qid in missing_queries:
      continue
    try:
      q = Query.objects.get(qid=qid)
    except Query.DoesNotExist:
      missing_queries.add(qid)
      if message_callback:
        message_callback('Query "%s" in Doc Pairs File does not exist' % qid)
      continue

    yield Document(query = q, document = doc, score = float(score))

def add_users(username_pattern='user%d', password_pattern=None, count=100):
  '''adds users programmatically, with username=password, following the
  pattern'''
  from django.contrib.auth.models import User
  if password_pattern is None:
    password_pattern = username_pattern

  for i in xrange(count):
    u = User( username = username_pattern % i )
    u.set_password( password_pattern % i )
    u.save()
