# Models for document relevance assessment app.
from django.db import models
from django.contrib.auth.models import User
from datetime import datetime
from assessment import app_settings

class Query(models.Model):
  '''A Query'''
  qid = models.CharField(max_length=100, unique=True)
  text = models.CharField(max_length=500)
  remaining_assignments = models.IntegerField(default=1)
  assigned_assessors = models.ManyToManyField(User,
                                              related_name='assigned_queries',
                                              through='Assignment')

  class Meta:
    verbose_name_plural = 'queries'

  def __unicode__(self):
    return '%s: %s' % (self.qid, self.text)

class Assignment(models.Model):
  '''An assignment of a query to an assessor.  Each assignment is also contains
  the information need data and provides access to the complete & pending
  assessments.'''
  assessor = models.ForeignKey(User, related_name='assignments')
  query =  models.ForeignKey(Query, related_name='assignments')
  created_date = models.DateTimeField('creation date', editable=False)
  # Time the info need was filled out.
  started_date = models.DateTimeField('started date', null=True, editable=False)
  # information need description fields:
  # NOTE: the description must be non-blank before any assessments can be
  # created for this assignment.
  description = models.TextField(blank=True)
  narrative = models.TextField(blank=True)

  class Meta:
    # make sure an assessor doesn't get assigned to the same query twice
    unique_together = ('assessor', 'query')

  def save(self):
    '''Custom save method that handles automatically filling in the dates'''
    if not self.id:
      self.created_date = datetime.now()
    if self.started_date == None and len(self.description) > 0:
      self.started_date = datetime.now()
    super(Assignment, self).save()

  @models.permalink
  def get_absolute_url(self):
    return ('assignment_detail', [str(self.id)])

  def num_assessments_complete(self):
    '''The number of assessments complete for this assignment.'''
    return self.assessments.count()

  def num_assessments_pending(self):
    '''The number of assessments pending for this assignment.'''
    return self.query.doc_pairs.count() - self.num_assessments_complete()

  def pending_query_doc_pairs(self):
    '''The assessments pending for this assignment.'''
    completed_ids = [ a.query_doc_pair.id for a in self.assessments.all() ]
    return self.query.doc_pairs.exclude(id__in=completed_ids)

  def complete(self):
    '''Boolean indicating whether all the assessments have been completed for
    this assignment.'''
    return len(self.description) > 0 and self.num_assessments_pending() == 0

  def latest_assessment(self):
    '''The most recent assessment, or None if no assessments have been
    completed'''
    all_assessments = self.assessments.all()
    if all_assessments.count() == 0:
      return None
    return all_assessments.order_by('-created_date')[0]

  def elapsed_time(self):
    '''The time elapsed between the population of the info need and the most
    recent assessment.  Returns None if no assessments have been completed.'''
    if self.started_date is None:
      return 0
    latest = self.latest_assessment()
    if self.complete() and latest:
      return latest.created_date - self.started_date
    else:
      return datetime.now() - self.started_date

  def status(self):
    '''Returns a string representation of the status of this assignment,
    showing whether the assignment is complete and if not, how many assessments
    are remaining.'''
    if self.complete():
      return 'Complete'
    elif len(self.description) == 0:
      return 'Not Started'
    else:
      return '%d / %d' % (self.num_assessments_complete(), \
                          self.query.doc_pairs.count())

  def __unicode__(self):
    return '%s assigned to %s' % (self.assessor, self.query)

class QueryDocumentPair(models.Model):
  '''A query-document pair.  Contains a reference to 'left' and 'right'
  documents, which will be referred to with the PreferenceAssessment'''
  query = models.ForeignKey(Query, related_name='doc_pairs')
  left_doc = models.CharField('left document', max_length=100)
  right_doc = models.CharField('right document', max_length=100)

  class Meta:
    # make sure we don't have the same pair in the DB twice
    unique_together = ('query', 'left_doc', 'right_doc')

  def qid(self):
    return self.query.qid

  def __unicode__(self):
    return '[%s] %s vs. %s' % (self.query.text, self.left_doc, self.right_doc)

class PreferenceAssessment(models.Model):
  '''A judgement on a query-document pair.  Supported judgements are left, right
  (to indicate the left or right documents are better) or "both bad" to
  indicate both documents are not at all relevant.'''
  # The choice values, and a swapped version for use in the form.
  PREFERENCE_CHOICES =     \
    ( ('L', 'Left'), ('B', 'Both Bad'), ('R', 'Right'), ('D', 'Duplicates') )
  REV_PREFERENCE_CHOICES = \
    ( ('R', 'Left'), ('B', 'Both Bad'), ('L', 'Right'), ('D', 'Duplicates') )
  assignment = models.ForeignKey(Assignment, related_name='assessments',
    # make sure we don't create any assessments for an assignment without an
    # info need description filled.
    limit_choices_to = ~models.Q(description__exact = ''))
  query_doc_pair = models.ForeignKey(QueryDocumentPair,
    related_name='assessments')
  created_date = models.DateTimeField('creation date', editable=False)
  preference = models.CharField(max_length=1, choices=PREFERENCE_CHOICES)
  # Indicates whether the documents should be swapped when displayed
  swap_docs = models.BooleanField(default=False)#, editable=False)

  # To hold the "Other" preference reason
  preference_reason_other = models.CharField(max_length=500, blank=True)

  class Meta:
    # only one judgement per query_doc_pair & assignment
    unique_together = ('assignment', 'query_doc_pair')

  @models.permalink
  def get_absolute_url(self):
    return ('assessment_detail', [str(self.id)])

  def get_choices(self):
    '''Returns the appropriate choices for a form given the value of
    swap_docs.'''
    if self.swap_docs: return self.REV_PREFERENCE_CHOICES
    else: return self.PREFERENCE_CHOICES

  def left_doc(self):
    '''Returns the (true) left document'''
    return self.query_doc_pair.left_doc

  def right_doc(self):
    '''Returns the (true) right document'''
    return self.query_doc_pair.right_doc

  def presented_left_doc(self):
    '''Returns the (possibly swapped) left document'''
    if self.swap_docs: return self.query_doc_pair.right_doc
    else: return self.query_doc_pair.left_doc

  def presented_right_doc(self):
    '''Returns the (possibly swapped) right document'''
    if self.swap_docs: return self.query_doc_pair.left_doc
    else: return self.query_doc_pair.right_doc

  def presented_left_doc_url(self):
    '''Returns the (possibly swapped) left document URL'''
    return app_settings.DOCSERVER_URL_PATTERN % self.left_doc()

  def presented_right_doc_url(self):
    '''Returns the (possibly swapped) right document URL'''
    return app_settings.DOCSERVER_URL_PATTERN % self.right_doc()

  def save(self):
    '''Custom save method that handles automatically filling in the dates'''
    if not self.id:
      self.created_date = datetime.now()
    super(PreferenceAssessment, self).save()

  def assessor(self):
    return self.assignment.assessor

  def query(self):
    return self.assignment.query

  def reasons_str(self):
    return ', '.join(unicode(r) for r in self.reasons.all())
  reasons_str.short_description = "Reasons"

  def __unicode__(self):
    try:
      left, right = self.left_doc(), self.right_doc()
    except QueryDocumentPair.DoesNotExist:
      return 'UNINITIALIZED'

    if self.preference == 'L':
      preferred, unpreferred = left, right
    elif self.preference == 'R':
      preferred, unpreferred = right, left
    elif self.preference == 'B':
      return '%s, %s both bad' % (left, right)
    else:
      return 'neither %s or %s' % (left, right)

    return '%s preferred over %s' % (preferred, unpreferred)

class PreferenceReason(models.Model):
  '''Options for selecting a preference assessment reason'''
  short_name = models.CharField(max_length=100, unique=True)
  description = models.CharField(max_length=500)
  active = models.BooleanField(default=True)

  def __unicode__(self):
    return self.short_name

class PreferenceAssessmentReason(models.Model):
  '''A reason for a particular preference assessment.'''
  assessment = models.ForeignKey(PreferenceAssessment, related_name='reasons')
  reason = models.ForeignKey(PreferenceReason)

  class Meta:
    unique_together = ('assessment', 'reason')

  def __unicode__(self):
    return self.reason.short_name

class Comment(models.Model):
  '''A simple comment on the assessment task.'''
  assessor = models.ForeignKey(User)
  comment = models.TextField()
  created_date = models.DateTimeField('creation date', editable=False)

  def save(self):
    '''Custom save method that handles automatically filling in the dates'''
    if not self.id:
      self.created_date = datetime.now()
    super(Comment, self).save()

  def __unicode__(self):
    return 'by %s on %s' % (self.assessor, self.created_date)
