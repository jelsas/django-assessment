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
from random import randint
from util import parse_queries_file, parse_docscores_file

pref_assessment_form_factory = PreferenceAssessmentReasonFormFactory()
strategy = BubbleSortStrategy(app_settings.ASSESSMENTS_PER_QUERY)

def redirect_to_pagename(request, pagename):
  return HttpResponseRedirect(reverse(pagename))

@login_required
@user_passes_test(lambda user: user.is_superuser)
def admin_dashboard(request):
  # calc some info for all the current & pending assignments
  current_assignments = [ \
    {'query': a.query, \
     'assessor': a.assessor, \
     'created_date': a.created_date, \
     'complete': a.num_assessments_complete(), \
     'pending': strategy.pending_assessments(a)} \
    for a in Assignment.objects.order_by('-created_date') ]
  pending_assignments = Query.objects.filter(remaining_assignments__gt = 0)
  return render_to_response('assessment/admin_dashboard.html', \
        { 'pending_assignments': pending_assignments, \
          'current_assignments': current_assignments }, \
        RequestContext(request))

@login_required
@user_passes_test(lambda user: user.is_superuser)
def upload_data(request):
  messages = []
  if request.method == 'POST':
    form = DataUploadForm(request.POST, request.FILES)
    if form.is_valid():
      # handle the queries form
      if 'queries_file' in request.FILES:
        query_count = 0
        for query in parse_queries_file(request.FILES['queries_file']):
          try:
            query.save()
          except IntegrityError:
            continue
          query_count += 1
        messages.append('Uploaded %d queries' % query_count)
      if 'document_pairs_file' in request.FILES:
        doc_count = 0
        for doc in parse_docscores_file(
              request.FILES['document_pairs_file'], messages.append):
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
                            {'data': PreferenceAssessment.objects.all()},
                            RequestContext(request), mimetype='text/csv')

@login_required
def assessor_dashboard(request):
  assignments = request.user.assignments.all()

  # Make lists of complete & in-progress assignments
  complete_assignments, pending_assignments = [], []
  for a in assignments:
    n_pending = strategy.pending_assessments(a)
    if n_pending == 0:
      complete_assignments.append(a)
    else:
      pending_assignments.append( {'assignment':a,
                                   'pending_assessments':n_pending} )


  # Grab a random query to offer
  assigned_query_ids = assignments.values_list('id', flat=True)
  try:
    available_query = \
      Query.objects.exclude(id__in=assigned_query_ids)\
        .filter(remaining_assignments__gt=0).order_by('?')[0]
  except IndexError:
    # no available queries for this assessor
    available_query = None

  # comment form
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
      # must be already assigned to this query, so bail here & go to the
      # assignment detail page
      return HttpResponseRedirect(reverse('assignment_detail',
                                  args=[assignment.id]))
    # decrement our remaining_assignments field
    query.remaining_assignments -= 1
    query.save()

    # copy all the docs for this query to AssessedDocument objects
    for doc in query.documents.all():
      assessed_doc = AssessedDocument(assignment=assignment,
                                      document=doc)
      assessed_doc.save()
    return HttpResponseRedirect(reverse('assignment_detail',
                                args=[assignment.id]))
  else:
    return render_to_response('assessment/select_query_confirm.html',
                              {'query': query}, RequestContext(request))

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
    return HttpResponseRedirect(reverse('assessor_dashboard'))
  # redirect to the new_assessment view now that we have all the docpair info
  return HttpResponseRedirect(reverse('new_assessment',
                              args = (assignment.id,) + docpair.to_args()))

@login_required
def new_assessment(request, assignment_id,
                   left_doc, left_fixed, right_doc, right_fixed):
  assignment = get_object_or_404(Assignment, pk=assignment_id)
  left_doc = get_object_or_404(AssessedDocument, pk=left_doc)
  right_doc = get_object_or_404(AssessedDocument, pk=right_doc)

  if request.method == 'POST':
    form = PreferenceAssessmentForm(request.POST)
    #reason_form = pref_assessment_form_factory.create(request.POST)
    if form.is_valid(): # and reason_form.is_valid():
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

  # TODO: make these options configurable in settings.py?
  #submit_options = [('Submit', '_save')]
  submit_options = [('Submit & Continue', '_continue')]
  #if assignment.num_assessments_pending() > 1:
  #  submit_options.append( ('Submit & Continue', '_continue') )
  #elif assignment.num_assessments_pending() == 1:
  #  submit_options.append( ('Submit & Return to Dashboard', '_complete') )

  return render_to_response('assessment/assessment_detail.html',
    {'assignment': assignment,
      'docpair': docpair,
      'form': PreferenceAssessmentForm(
                      initial={'left_doc':docpair.docs[0].id,
                               'right_doc':docpair.docs[1].id}),
      #'reason_form': pref_assessment_form_factory.create(),
      'pending_assessments':strategy.pending_assessments(assignment),
      'submit_options': submit_options},
    RequestContext(request))

@login_required
def assessment_detail(request, assessment_id):
  '''To handle updating a previously entered assessment'''
  assessment = get_object_or_404(AssessedDocumentRelation, pk=assessment_id)
  if assessment.assignment().assessor != request.user:
    return render_to_response('assessment/access_error.html',
      {'message': 'Sorry, you don\'t have permission to view this assessment'},
      RequestContext(request))

  if request.method == 'POST':
    form = PreferenceAssessmentForm(request.POST)
    #reason_form = pref_assessment_form_factory.create(request.POST)
    if form.is_valid():# and reason_form.is_valid():
      new_assessment = form.to_assessment()
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
      #assessment.reasons = new_assessment.reasons
      assessment.source_presented_left = new_assessment.source_presented_left
      #assessment.preference_reason_other = reason_form.cleaned_data['other']
      assessment.save()


      # update the checked reasons
      #existing_assessment_reasons = assessment.reasons
      #existing_ids = set( r.reason.id for r in \
      #                    existing_assessment_reasons.all() )
      #new_reasons = reason_form.checked_reasons()
      #new_ids = set( r.id for r in new_reasons )
      # delete existing reasons that aren't checked any more
      #for r in existing_assessment_reasons.exclude(reason__id__in=new_ids):
      #  r.delete()
      # add new ones that aren't in the existing reasons
      #for r in new_reasons.exclude(id__in=existing_ids):
      #  assessment_reason = PreferenceAssessmentReason(
      #    assessment = assessment,
      #    reason = r)
      #  assessment_reason.save()

      if '_continue' in request.POST:
        return HttpResponseRedirect(reverse('next_assessment',
                                            args=[assessment.assignment().id]))
      elif '_save' in request.POST:
        return HttpResponseRedirect(reverse('next_assessment',
                                            args=[assessment.assignment().id]))
        #return HttpResponseRedirect(reverse('assessment_detail',
        #                                    args=[assessment.id]))

  form = PreferenceAssessmentForm.from_assessment(assessment)
  #reason_form = pref_assessment_form_factory.create_from_assessment(assessment)

  submit_options = [('Submit', '_save')]
  #if assessment.assignment().num_assessments_pending() > 0:
  #  submit_options.append( ('Submit & Assess More', '_continue') )

  return render_to_response('assessment/assessment_detail.html',
    {'form': form,
      #'reason_form': reason_form,
      'docpair': DocumentPairPresentation.from_assessment(assessment),
      'assessment': assessment,
      'assignment': assessment.assignment(),
      'pending_assessments':strategy.pending_assessments(assessment.assignment()),
      'submit_options': submit_options},
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
