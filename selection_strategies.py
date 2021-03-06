from assessment.models import Assignment
from assessment import app_settings

def _choose_2(n):
  return 0 if n < 2 else n * (n-1) / 2

class DocumentPairPresentation(object):
  '''Deals with which document is presented on the left/right and which
  document is fixed in place from the last presentation.'''
  def __init__(self, left_doc, right_doc, left_fixed, right_fixed):
    # the docs tuple contains AssessedDocument objects
    self.docs = (left_doc, right_doc)
    self.fixed = (left_fixed, right_fixed)

  def left_fixed(self):
    return self.fixed[0]

  def right_fixed(self):
    return self.fixed[1]

  def left_doc(self):
    return self.docs[0].document.document

  def right_doc(self):
    return self.docs[1].document.document

  def times_left_assessed(self):
    return self.docs[0].n_times_assessed()

  def times_right_assessed(self):
    return self.docs[1].n_times_assessed()

  def left_doc_url(self):
    return app_settings.DOCSERVER_URL_PATTERN % self.left_doc()

  def right_doc_url(self):
    return app_settings.DOCSERVER_URL_PATTERN % self.right_doc()

  @classmethod
  def from_assessment(cls, assessment):
    if assessment.source_presented_left:
      left_doc = assessment.source_doc
      right_doc = assessment.target_doc
    else:
      left_doc = assessment.target_doc
      right_doc = assessment.source_doc
    return cls(left_doc, right_doc, False, False)

  def to_args(self):
    '''returns a tuple of (left_doc, left_fixed, right_doc, right_fixed) for
    use with the new_assessment view'''
    if self.fixed[0]: lf = '+'
    else: lf = ''
    if self.fixed[1]: rf = '+'
    else: rf = ''

    return (self.docs[0].id, lf, self.docs[1].id, rf)

class Strategy(object):
  '''A simple strategy that just returns random pairs of documents with
  no regard for the assignment history.'''
  assume_transitivity = False

  def __init__(self, max_assessments_per_query):
    self.max_assessments_per_query = max_assessments_per_query

  def next_pair(self, assignment):
    return None

  def assignment_complete(self, assignment):
    return self.pending_assessments(assignment) <= 0

  def pending_assessments(self, assignment):
    if assignment.complete: return 0
    assessments_done = \
                assignment.num_assessments_complete(self.assume_transitivity)
    if assessments_done >= self.max_assessments_per_query:
      # this assignment should be marked complete
      assignment.complete = True
      assignment.save()
      return 0
    n_docs = assignment.documents.count()
    n_bad_dups = len(assignment.bad_documents() | assignment.dup_documents())
    # preference assessments only (not bad or dup judgements):
    prefs_done = assessments_done - n_bad_dups
    # total pref assessments given the number of bads & dups
    prefs_possible = min(self.max_assessments_per_query - n_bad_dups, \
                          _choose_2(n_docs - n_bad_dups))
    max_remaining_assessments = prefs_possible - prefs_done
    return max(max_remaining_assessments, 0)

  def doc_slots(self, assignment):
    if assignment.relation_type == 'B':
      if assignment.source_presented_left:
        return [None, assignment.target_doc]
      else:
        return [assignment.target_doc, None]
    else:
      if assignment.source_presented_left:
        return [assignment.source_doc, None]
      else:
        return [None, assignment.source_doc]

  def new_pair(self, assignment, order_by = '?'):
    '''Gets a pair of documents, using the ordering relation specified.'''
    available_docs = assignment.available_documents().order_by(order_by)
    for next_doc in available_docs:
      available_others = next_doc.available_pairs(self.assume_transitivity)
      if available_others.exists():
        return DocumentPairPresentation(next_doc, available_others[0],
                                        False, False)
    # we haven't found any suitable new pair, so we may be done
    return None

class BubbleSortStrategy(Strategy):

  '''A strategy that performs a Bubble Sort type selection, with the goal of
  exposing the assessor to the whole document set as soon as possible, finding
  the 'best' document in a single pass, and keeping one document in the pair
  fixed to the greatest extent possible.'''
  def next_pair(self, assignment):
    if self.assignment_complete(assignment): return None
    latest_assessment = assignment.latest_assessment()
    if latest_assessment is None:
      # just grab the first 2 docs for assessment
      return self.new_pair(assignment, order_by='-document__score')

    if latest_assessment.relation_type == 'B':
      keep_doc = latest_assessment.target_doc
      keep_left = not latest_assessment.source_presented_left
    else:
      keep_doc = latest_assessment.source_doc
      keep_left = latest_assessment.source_presented_left

    if app_settings.MAX_ASSESSMENTS_PER_DOC > 0 and \
        keep_doc.n_times_assessed() >= app_settings.MAX_ASSESSMENTS_PER_DOC:
      # just grab the next 2 docs for assessment
      return self.new_pair(assignment, order_by='-document__score')

    # find the next document in the pair.  First, favor documents that haven't
    # been judged at all, then favor docs. that haven't been judged with the
    # keep_doc
    other_docs = assignment.unassessed_documents()
    if other_docs.exists():
      other_doc = other_docs.order_by('-document__score')[0]
    else:
      other_docs = keep_doc.available_pairs(self.assume_transitivity)
      if other_docs.exists():
        other_doc = other_docs.order_by('-document__score')[0]
      else:
        other_doc = None

    if other_doc:
      if keep_left:
        return DocumentPairPresentation(keep_doc, other_doc, True, False)
      else:
        return DocumentPairPresentation(other_doc, keep_doc, False, True)
    else:
      # there weren't any available other documents with this one, so do
      # a new pair
      return self.new_pair(assignment, order_by='-document__score')
