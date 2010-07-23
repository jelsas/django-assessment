from django.db.models import Sum
from django.core.cache import cache
from assessment.models import Assignment, Query, PreferenceAssessment
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

class Progress(object):
  def total(self): return 0
  def complete(self): return 0
  def assigned(self): return 0

  def google_chart_argument(self):
    '''Returns a string suitable for use in a google chart API call.'''
    total, complete, assigned = self.total(), self.complete(), self.assigned()
    if total > 0:
      complete_scaled = 100 * complete / total
      assigned_incomplete_scaled = 100 * (assigned - complete) / total
      unassigned_scaled = 100 * (total - assigned) / total
      return '%d|%d|%d' % \
        (complete_scaled, assigned_incomplete_scaled, unassigned_scaled)
    else:
      return '0|0|100'

class AssignmentProgress(Progress):
  @my_cache
  def total(self):
    return Assignment.objects.count() + Query.objects.aggregate( \
        Sum('remaining_assignments'))['remaining_assignments__sum']

  @my_cache
  def complete(self):
    return sum( 1 for a in Assignment.objects.all() if a.complete() )

  @my_cache
  def assigned(self):
    return Assignment.objects.count()

class AssessmentProgress(Progress):
  @my_cache
  def total(self):
    unassigned = sum((q.remaining_assignments * q.doc_pairs.count()) \
        for q in Query.objects.filter(remaining_assignments__gt=0).all() )
    return self.assigned() + unassigned

  @my_cache
  def complete(self):
    return PreferenceAssessment.objects.count()

  @my_cache
  def assigned(self):
    return sum(a.query.doc_pairs.count() for a in Assignment.objects.all())
