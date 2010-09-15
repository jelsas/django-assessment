from assessment.models import Assignment
from assessment import app_settings

class DocumentPairPresentation(object):
  '''Deals with which document is presented on the left/right and which
  document is fixed in place from the last presentation.'''
  def __init__(self, left_doc, right_doc, left_fixed, right_fixed):
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

class Strategy(object):
  '''A simple strategy that just returns random pairs of documents with
  no regard for the assignment history.'''
  def __init__(self, max_assessments_per_query):
    self.max_assessments_per_query = max_assessments_per_query

  def next_pair(self, assignment):
    return None

  def assignment_complete(self, assignment):
    return self.pending_assessments(assignment) <= 0

  def pending_assessments(self, assignment):
    assessments_done = assignment.num_assessments_complete()
    n_docs = assignment.available_documents().count()
    max_for_this_assignment = min((n_docs * (n_docs - 1))/2, \
                                  self.max_assessments_per_query)
    return max(max_for_this_assignment - assessments_done, 0)

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
      docs = assignment.available_documents().order_by('-document__score')[0:2]
      return DocumentPairPresentation(docs[0], docs[1], False, False)

    if latest_assessment.relation_type == 'B':
      keep_doc = latest_assessment.target_doc
      keep_left = not latest_assessment.source_presented_left
    else:
      keep_doc = latest_assessment.source_doc
      keep_left = latest_assessment.source_presented_left

    # find all the documents that have been judged with keep_doc
    # and find the highest scoring one not in that set
    candidate_pairs = keep_doc.available_pairs()

    if candidate_pairs.count() > 0:
      if keep_left:
        return DocumentPairPresentation(keep_doc, \
          candidate_pairs.order_by('-document__score')[0], True, False)
      else:
        return DocumentPairPresentation(\
          candidate_pairs.order_by('-document__score')[0],
          keep_doc, False, True)
    else:
      # there weren't any available other documents with this one, so pick
      # anther doc
      for doc in assignment.available_documents().order_by('-document__score'):
        candidate_pairs = doc.available_pairs()
        if candidate_pairs.count() > 0:
          return DocumentPairPresentation( \
            candidate_pairs.order_by('-document__score')[0], doc, False, False )
    # couldn't find anything, so maybe we're done
    return None
