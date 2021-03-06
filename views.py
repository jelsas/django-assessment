from assessment.models import *
from assessment.forms import *
from assessment.selection_strategies import BubbleSortStrategy, \
                                            DocumentPairPresentation
from assessment import app_settings
from django.core.urlresolvers import reverse
from django.db import IntegrityError
from django.db.models import Sum
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render_to_response, \
                             get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.template import RequestContext
from random import randint, uniform
from util import parse_queries_file, parse_docscores_file

pref_assessment_form_factory = PreferenceAssessmentReasonFormFactory()
strategy = BubbleSortStrategy(app_settings.ASSESSMENTS_PER_QUERY)
strategy.assume_transitivity = app_settings.ASSUME_TRANSITIVITY

def redirect_to_pagename(request, pagename):
  return HttpResponseRedirect(reverse(pagename))

@login_required
@user_passes_test(lambda user: user.is_superuser)
def admin_dashboard(request):
  # group data by query
  queries = []
  for q in Query.objects.all():
    q_data = { 'query': q, \
               'remaining_assignments': q.remaining_assignments, \
               'assignments': [] }
    for a in q.assignments.all():
      q_data['assignments'].append( { \
          'assessor': a.assessor, \
          'id': a.id, \
          'created_date': a.created_date, \
          'complete': a.num_assessments_complete(), \
          'pending': strategy.pending_assessments(a) } )
    queries.append(q_data)
  return render_to_response('assessment/admin_dashboard.html', \
        { 'queries': queries}, RequestContext(request))

@login_required
@user_passes_test(lambda user: user.is_superuser)
def upload_data(request):
  messages = []
  if request.method == 'POST':
    form = DataUploadForm(request.POST, request.FILES)
    if form.is_valid():
      # handle queries
      if 'queries_file' in request.FILES:
        query_count = 0
        for query in parse_queries_file(request.FILES['queries_file']):
          try:
            query.remaining_assignments = form.cleaned_data['assignments']
            query.save()
          except IntegrityError:
            continue
          query_count += 1
        messages.append('Uploaded %d queries' % query_count)

      # handle documents
      if 'document_scores_file' in request.FILES:
        doc_count = 0
        for doc in parse_docscores_file(
              request.FILES['document_scores_file'], messages.append):
          if form.cleaned_data['randomize_document_presentation']:
            # assign a random number to the score
            doc.score = uniform(0, 1)
          try:
            doc.save()
          except IntegrityError:
            continue
          doc_count += 1
        messages.append('Uploaded %d docs' % doc_count)

  else:
    form = DataUploadForm()
  return render_to_response('assessment/upload_data.html',
                            {'messages': messages, 'form': form},
                            RequestContext(request))

@login_required
@user_passes_test(lambda user: user.is_superuser)
def download_data(request):
  return render_to_response('assessment/data_download.txt',
                            {'data': AssessedDocumentRelation.objects.all()},
                            RequestContext(request), mimetype='text/csv')

@login_required
def assessor_dashboard(request):
  assignments = request.user.assignments.all()

  # Make lists of complete & in-progress assignments
  complete_assignments, pending_assignments = [], []
  for a in assignments.filter(abandoned=False):
    n_pending = strategy.pending_assessments(a)
    if n_pending == 0:
      complete_assignments.append(a)
    else:
      pending_assignments.append( {'assignment':a,
                                   'pending_assessments':n_pending} )


  # Grab a random query to offer
  assigned_query_ids = assignments.values_list('query__id', flat=True)
  try:
    available_query = \
      Query.objects.exclude(id__in=assigned_query_ids)\
        .filter(remaining_assignments__gt=0).order_by('?')[0]
  except IndexError:
    # no available queries for this assessor
    available_query = None

  comment_form = CommentForm()

  data = { 'complete_assignments': complete_assignments,
           'pending_assignments': pending_assignments,
           'available_query': available_query,
           'comment_form': comment_form}

  return render_to_response('assessment/assessor_dashboard.html', data,
    RequestContext(request))

@login_required
def information_need(request, assignment_id):
  '''Handles viewing/updating the information need description.'''
  assignment = get_object_or_404(Assignment, pk=assignment_id)
  if assignment.assessor != request.user:
    return render_to_response('assessment/access_error.html',
      {'message': 'This query has not been assigned to you.'},
      RequestContext(request))

  if request.method == 'POST':
    form = InformationNeedForm(request.POST)
    if form.is_valid():
      assignment.description = form.cleaned_data['description']
      assignment.narrative = form.cleaned_data['narrative']
      assignment.save()
      return HttpResponseRedirect(request.REQUEST['next'])

  form = InformationNeedForm(instance=assignment)
  return render_to_response('assessment/assignment_infoneed.html',
    {'assignment':assignment, 'form': form, 'next': request.REQUEST['next']},
    RequestContext(request))

@login_required
def select_query_confirm(request, query_id):
  '''Handles confirmation of query assignment.'''
  query = get_object_or_404(Query, pk=query_id)

  if request.method == 'POST':
    # create a new assignment
    assignment = Assignment(assessor = request.user,
                            query = query)
    try:
      assignment.save()
    except IntegrityError:
      # must be already assigned to this query, so start assessing
      assignment = Assignment.objects.get(assessor = request.user,
                            query = query)
      return HttpResponseRedirect(reverse('next_assessment',
                                args=[assignment.id]))
    # decrement our remaining_assignments field
    query.remaining_assignments -= 1
    query.save()

    # copy all the docs for this query to AssessedDocument objects
    for doc in query.documents.all():
      assessed_doc = AssessedDocument(assignment=assignment,
                                      document=doc)
      assessed_doc.save()
    return HttpResponseRedirect(reverse('next_assessment',
                                args=[assignment.id]))
  else:
    return render_to_response('assessment/select_query_confirm.html',
                              {'query': query}, RequestContext(request))

@login_required
def abandon_query_confirm(request, assignment_id):
  '''Handles confirmation of abandoning a query assignment.'''
  a = get_object_or_404(Assignment, pk=assignment_id)

  if request.method == 'POST':
    # mark abandoned
    a.abandoned = True
    a.save()

    # increment the remaining_assignments field
    query = a.query
    query.remaining_assignments += 1
    query.save()

    return HttpResponseRedirect(reverse('assessor_dashboard'))
  else:
    return render_to_response('assessment/abandon_query_confirm.html',
                              {'assignment': a}, RequestContext(request))

@login_required
def assignment_detail(request, assignment_id):
  a = get_object_or_404(Assignment, pk=assignment_id)
  # make sure this assessor is actually assigned to this query
  if a.assessor != request.user and not request.user.is_superuser:
    return render_to_response('assessment/access_error.html',
      {'message': 'Sorry, you don\'t have permission to view this assignment'},
      RequestContext(request))

  # use the selection strategy to calculate the number of remaining assessments
  return render_to_response('assessment/assignment_detail.html',
    {'assignment': a, 'pending_assessments':strategy.pending_assessments(a)},
    RequestContext(request))

@login_required
def next_assessment(request, assignment_id):
  '''This view is responsible for getting the next document to assess.  It
  doesn't actually save anything'''
  assignment = get_object_or_404(Assignment, pk=assignment_id)
  if assignment.assessor != request.user:
    return render_to_response('assessment/access_error.html',
      {'message': 'Sorry, you don\'t have permission to view this assignment'},
      RequestContext(request))

  docpair = strategy.next_pair(assignment)
  # if no docpairs, we must be done
  if docpair is None:
    assignment.complete = True
    assignment.save()
    return HttpResponseRedirect(reverse('assessor_dashboard'))

  new_assessment_url = reverse('new_assessment',
                              args = (assignment.id,) + docpair.to_args())
  # If we're collecting information need statements, make sure we do this before
  # collecting any assessments
  if app_settings.COLLECT_INFORMATION_NEED and len(assignment.description) == 0:
    return HttpResponseRedirect(reverse('information_need',
                    args = (assignment.id,)) + '?next=' + new_assessment_url)
  return HttpResponseRedirect(new_assessment_url)

@login_required
def new_assessment(request, assignment_id,
                   left_doc, left_fixed, right_doc, right_fixed):
  assignment = get_object_or_404(Assignment, pk=assignment_id)

  # first make sure we have the information need filled
  if app_settings.COLLECT_INFORMATION_NEED and len(assignment.description) == 0:
    return HttpResponseRedirect(reverse('information_need',
                    args = (assignment_id,)) + '?next=' + request.path)

  left_doc = get_object_or_404(AssessedDocument, pk=left_doc)
  right_doc = get_object_or_404(AssessedDocument, pk=right_doc)

  if request.method == 'POST':
    form = PreferenceAssessmentForm(request.POST)
    if form.is_valid():
      # create a new AssessedDocumentRelation
      rel = form.to_assessment(left_doc, right_doc)
      try:
        rel.save()
      except IntegrityError:
        # the assessor must have gone back to this page, after having submitted
        # once already.  find that previous assessment & update it
        existing_assessment = AssessedDocumentRelation.objects.get( \
          source_doc = rel.source_doc, target_doc = rel.target_doc)
        existing_assessment.relation_type = rel.relation_type
        existing_assessment.save()
      # go to the next one
      return HttpResponseRedirect(reverse('next_assessment',
                                  args=(assignment_id,)))

  docpair = DocumentPairPresentation(left_doc, right_doc,
                                    left_fixed == '+', right_fixed == '+')

  submit_options = [('Submit & Continue', '_continue')]

  return render_to_response('assessment/assessment_detail.html',
    {'assignment': assignment,
      'docpair': docpair,
      'form': PreferenceAssessmentForm(
                      initial={'left_doc':docpair.docs[0].id,
                               'right_doc':docpair.docs[1].id}),
      'pending_assessments':strategy.pending_assessments(assignment),
      'submit_options': submit_options},
    RequestContext(request))

@login_required
def assessment_detail(request, assessment_id):
  '''To handle updating a previously entered assessment'''
  assessment = get_object_or_404(AssessedDocumentRelation, pk=assessment_id)
  is_assigned_user = assessment.assignment().assessor == request.user
  if not ( is_assigned_user or request.user.is_superuser ):
    return render_to_response('assessment/access_error.html',
      {'message': 'Sorry, you don\'t have permission to view this assessment'},
      RequestContext(request))

  if request.method == 'POST' and is_assigned_user:
    form = PreferenceAssessmentForm(request.POST)
    if form.is_valid():
      left_doc = assessment.source_doc if assessment.source_presented_left \
                                       else assessment.target_doc
      right_doc = assessment.target_doc if assessment.source_presented_left \
                                        else assessment.source_doc

      new_assessment = form.to_assessment(left_doc, right_doc)
      if assessment.source_doc != new_assessment.source_doc or \
          assessment.target_doc != new_assessment.target_doc:
        # someone was monkeying with the form (or the ID in the URL) and the
        # assessment to be saved doesn't match what was in the URL.
        # so we'll just ignore this, log an error,
        # and go to the next assessment
        message = '''
          user %s
          assessment %s
          %s != %s (source)
          %s != %s (target)''' % (request.user, str(assessment.id),
                              assessment.source_doc, new_assessment.source_doc,
                              assessment.target_doc, new_assessment.target_doc)
        mail_admins('Error saving assessment from user %s' % request.user,
            message)
        return HttpResponseRedirect(reverse('next_assessment',
                                    args=[assessment.assignment().id]))

      assessment.relation_type = new_assessment.relation_type
      assessment.source_presented_left = new_assessment.source_presented_left
      assessment.save()

      if '_continue' in request.POST:
        return HttpResponseRedirect(reverse('next_assessment',
                                            args=[assessment.assignment().id]))
      elif '_save' in request.POST:
        return HttpResponseRedirect(reverse('next_assessment',
                                            args=[assessment.assignment().id]))

  form = PreferenceAssessmentForm.from_assessment(assessment)
  if not is_assigned_user:
    form.fields['preference'].widget.attrs['disabled'] = 'true'

  return render_to_response('assessment/assessment_detail.html',
    {'form': form,
      'docpair': DocumentPairPresentation.from_assessment(assessment),
      'assessment': assessment,
      'assignment': assessment.assignment(),
      'pending_assessments':strategy.pending_assessments(assessment.assignment())},
    RequestContext(request))

@login_required
def comment(request):
  '''Handles leaving a comment.'''
  if request.method == 'POST':
    form = CommentForm(request.POST)
    if form.is_valid():
      comment = Comment(assessor = request.user,
                        comment = form.cleaned_data['message'])
      comment.save()
      message = 'Thank you for your comment.'
      form = None
    else:
      message = 'Error saving comment.  Please try again.'
  else:
    message = None
    # clear the form for another comment
    form = CommentForm()
  return render_to_response('assessment/comment.html',
    {'message': message, 'form': form}, RequestContext(request))
