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

  def doc_judgement_counts(self):
    docs = self.query.documents.all()
    doc_counts = []
    for d in docs:
      matching_assessments = self.assessments().filter(left_doc = d) \
                            | self.assessments().filter(right_doc = d)
      doc_counts.append( (d, matching_assessments.count()) )
    return doc_counts

  @models.permalink
  def get_absolute_url(self):
    return ('assignment_detail', [str(self.id)])

  def num_assessments_complete(self):
    '''The number of assessments complete for this assignment.'''
    return self.assessments().count()

  def latest_assessment(self):
    '''The most recent assessment, or None if no assessments have been
    completed'''
    all_assessments = self.assessments()
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

  def assessments(self):
    '''Returns all the AssessedDocumentRelation objects associated with this
    assignment.'''
    docs = self.documents.values('id')
    assessments = AssessedDocumentRelation.objects.filter(source_doc__in=docs)
    return assessments

  def available_documents(self):
    '''All documents that haven't been judged as bad, or as a duplicate'''
    assessments = self.assessments()
    bad_documents = set( \
      assessments.filter(relation_type = 'B').values_list('source_doc', \
                                                          flat=True))
    dup_documents = set( \
      assessments.filter(relation_type = 'D').values_list('target_doc', \
                                                          flat=True))
    return self.documents.exclude(id__in = bad_documents | dup_documents)

  def __unicode__(self):
    return '%s assigned to %s' % (self.assessor, self.query)

class Document(models.Model):
  '''A query-document pair.'''
  query = models.ForeignKey(Query, related_name='documents')
  document = models.CharField('document', max_length=300)
  score = models.FloatField('score', blank=True)

  class Meta:
    # make sure we don't have the same pair in the DB twice
    unique_together = ('query', 'document')

  def qid(self):
    return self.query.qid

  def __unicode__(self):
    return '[%s] %s' % (self.query.text, self.document)

class AssessedDocument(models.Model):
  assignment = models.ForeignKey(Assignment, related_name='documents')
  document = models.ForeignKey(Document)
  # The related_to field contains all document relations, including preference,
  # duplicate and bad-document judgements
  relations = models.ManyToManyField('self', symmetrical=False,
                                     through='AssessedDocumentRelation')

  def is_bad(self):
    '''Indicates whether the document has been judged bad.'''
    return self.as_source.exists(relation_type = 'B')

  def is_dup(self):
    '''Indicates whether the document has been judged a duplicate.'''
    return self.as_target.exists(relation_type = 'D')

  def n_times_preferred(self):
    '''The number of times this document is preferred to other documents'''
    return self.as_source.filter(relation_type = 'P').count()

  def n_times_nonpreferred(self):
    '''The number of times this document is preferred to other documents'''
    return self.as_target.filter(relation_type = 'P').count()

  def preferred_to(self):
    '''The documents this document is preferred to'''
    return self.as_source.filter(relation_type = 'P').values_list( \
                                'target_doc', flat=True)

  def judged_with(self):
    '''The other documents this doc. has been presented with'''
    return set(self.as_source.values_list('target_doc', flat=True)) | \
            set(self.as_target.values_list('source_doc', flat=True))

  def available_pairs(self):
    '''The other documents that aren't bad or duplicates that this document
    can be judged with'''
    available = self.assignment.available_documents() # excludes bad & dups
    available = available.exclude(id = self.id) # exclude self
    available = available.exclude(id__in = self.judged_with()) # exclude jud. w/
    return available

  class Meta:
    unique_together = ('assignment', 'document')

  def __unicode__(self):
    return 'doc %s, assignment %s' % (self.document, self.assignment)

class AssessedDocumentRelation(models.Model):
  '''Represents all assessments for documents, including preferences,
  duplicates, and 'bad' judgements.'''
  RELATION_TYPES = ( ('P', 'Preferred To'), ('D', 'Duplicate Of'),
                     ('B', 'Bad') )
  # TODO: ensure source_doc.assignment == target_doc.assignment
  # NOTE: when the relation is B, refers to the source_doc, and the target_doc
  #       is just used as a placeholder for calculating the "next assessment"
  source_doc = models.ForeignKey('AssessedDocument', related_name='as_source')
  target_doc = models.ForeignKey('AssessedDocument', related_name='as_target')
  created_date = models.DateTimeField('started date', editable=False)
  relation_type = models.CharField(max_length=1, choices=RELATION_TYPES)
  reasons = models.ManyToManyField('PreferenceReason', blank=True,
                                    related_name='relations')
  source_presented_left = models.BooleanField(default=True)

  def assignment(self):
    return self.source_doc.assignment

  def save(self):
    '''Custom save method that handles automatically filling in the date'''
    if not self.id:
      self.created_date = datetime.now()
    super(AssessedDocumentRelation, self).save()

  class Meta:
    unique_together = ('source_doc', 'target_doc')

  def __unicode__(self):
    if self.relation_type == 'P':
      return '[%s] document %s preferred to %s' % \
        (self.source_doc.assignment.query,
         self.source_doc.document.document,
         self.target_doc.document.document)
    elif self.relation_type == 'D':
      return '[%s] document %s duplicate of %s' % \
        (self.source_doc.assignment.query,
         self.source_doc.document.document,
         self.target_doc.document.document)
    elif self.relation_type == 'B':
      return '[%s] document %s is bad' % \
        (self.source_doc.assignment.query,
         self.source_doc.document.document)

class PreferenceReason(models.Model):
  '''Options for selecting a preference assessment reason'''
  short_name = models.CharField(max_length=100, unique=True)
  description = models.CharField(max_length=500)
  active = models.BooleanField(default=True)

  def __unicode__(self):
    return self.short_name

class Comment(models.Model):
  '''A simple comment on the assessment task.'''
  # TODO: add a 'hook' to email comments to administrator
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
