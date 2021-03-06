# Models for document relevance assessment app.
from django.db import models
from django.contrib.auth.models import User
from django.core.mail import mail_admins
from django.db.models import Count
from datetime import datetime
from assessment import app_settings

def _flatten(listOfLists):
  "Flatten one level of nesting"
  from itertools import chain
  # from http://docs.python.org/library/itertools.html
  return chain.from_iterable(listOfLists)

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

  # flag indicating this query assignment has been abandoned
  abandoned = models.BooleanField(default=False)

  # flag indicating whether the assignment is complete, to avoid re-calculating
  # this again & again
  complete = models.BooleanField(default=False)

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

  def num_assessments_complete(self, assume_transitivity = False):
    '''The number of assessments complete for this assignment.'''
    if assume_transitivity:
      g = self.assessment_graph()
      return len(g.all_path_lengths())
    else:
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

  def assessment_graph(self):
    '''Returns a joepy.graph.Graph version of the document assessments, with the
    (internal) document ID as the vertex labels.  Bad documents are not added
    to the graph, and Duplicates relations are added both directions with a zero
    weight.  Preferences are added with a weight of 1.0'''
    from joepy.graph import Graph
    g = Graph()
    for a in self.assessments():
      if a.relation_type == 'D':
        g.add_edge(a.source_doc.id, a.target_doc.id, 0)
        g.add_edge(a.target_doc.id, a.source_doc.id, 0)
      elif a.relation_type == 'P':
        g.add_edge(a.source_doc.id, a.target_doc.id, 1)
    return g

  def bad_documents(self):
    '''returns a set of bad document ids'''
    return set( \
      self.assessments().filter(relation_type = 'B').values_list('source_doc', \
                                                          flat=True))
  def dup_documents(self):
    '''returns a set of bad document ids'''
    return set( \
      self.assessments().filter(relation_type = 'D').values_list('target_doc', \
                                                          flat=True))

  def available_documents(self):
    '''All documents that haven't been judged as bad, or as a duplicate, and
    also haven't been judged more than MAX_ASSESSMENTS_PER_DOC times.'''
    assessments = self.assessments()
    docs = self.documents.exclude( id__in = self.bad_documents() | \
                                            self.dup_documents() )
    if app_settings.MAX_ASSESSMENTS_PER_DOC > 0:
      docs = docs.annotate(src_count=Count('as_source'), \
                          tar_count=Count('as_target'))
      # there's probably a way to do this without explicitly looping over all
      # documents, but I can't figure it out.
      docs = (d.id for d in docs if  \
        (d.src_count + d.tar_count) <= app_settings.MAX_ASSESSMENTS_PER_DOC)
      # make sure we return a QuerySet, not a list
      docs = self.documents.filter(id__in=docs)
    return docs

  def unassessed_documents(self):
    '''Documents that have not been judged at all'''
    assessed_docs = set(_flatten( \
        self.assessments().values_list('source_doc', 'target_doc')))
    return self.documents.exclude(id__in = assessed_docs)

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

  def n_times_assessed(self):
    '''The number of times this document was assessed with any other document'''
    return self.as_source.count() + self.as_target.count()

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

  def transitively_judged_with(self):
    '''All documents transitively preferred (or unpreferred) to this one'''
    g = self.assignment.assessment_graph()
    reachable = g.reachable_from(self.id)
    g.reverse()
    reachable = reachable | g.reachable_from(self.id)
    return reachable

  def available_pairs(self, assume_transitivity = False):
    '''The other documents that aren't bad or duplicates that this document
    can be judged with'''
    available = self.assignment.available_documents() # excludes bad & dups
    available = available.exclude(id = self.id) # exclude self
    if assume_transitivity:
      judged_with = self.transitively_judged_with()
    else:
      judged_with = self.judged_with()
    available = available.exclude(id__in = judged_with) # exclude jud. w/
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

  def assessor(self):
    return self.assignment().assessor

  def source_docname(self):
    return self.source_doc.document.document

  def target_docname(self):
    return self.target_doc.document.document

  def query(self):
    return self.assignment().query

  def save(self):
    '''Custom save method that handles automatically filling in the date'''
    if not self.id:
      self.created_date = datetime.now()
    super(AssessedDocumentRelation, self).save()

  @models.permalink
  def get_absolute_url(self):
    return ('assessment_detail', [str(self.id)])

  def relation_type_as_permalink(self):
    return '<a href="%s">%s</a>' % (self.get_absolute_url(), \
                                    self.get_relation_type_display())
  relation_type_as_permalink.allow_tags = True
  relation_type_as_permalink.short_description = 'Relation type'

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
  assessor = models.ForeignKey(User)
  comment = models.TextField()
  created_date = models.DateTimeField('creation date', editable=False)

  def save(self):
    '''Custom save method that handles automatically filling in the dates'''
    if not self.id:
      self.created_date = datetime.now()
    super(Comment, self).save()
    # send an email to the administrator.  this should be a signal, but
    # it isn't
    mail_admins('New Assessment Comment',
        'from: %s\ndate: %s\ncomment: %s\n' % \
          (self.assessor, self.created_date, self.comment))


  def __unicode__(self):
    return 'by %s on %s' % (self.assessor, self.created_date)
