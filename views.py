from assessment.models import *
from assessment.forms import *
from assessment.util import AssignmentProgress, AssessmentProgress
from django.core.urlresolvers import reverse
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render_to_response, \
                             get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.template import RequestContext
from random import randint

pref_assessment_form_factory = PreferenceAssessmentReasonFormFactory()
assessment_progress = AssessmentProgress()
assignment_progress = AssignmentProgress()

def redirect_to_pagename(request, pagename):
  return HttpResponseRedirect(reverse(pagename))

@login_required
@user_passes_test(lambda user: user.is_superuser)
def admin_dashboard(request):
  data = {'assessment_progress': assessment_progress,
          'assignment_progress': assignment_progress}

  return render_to_response('assessment/admin_dashboard.html', data,
                            RequestContext(request))

@login_required
@user_passes_test(lambda user: user.is_superuser)
def upload_data(request):
  # upload formats:
  # for queries file, <qid>:<query_text>
  # for docpairs file, <qid>:<left_doc>:<right_doc>
  messages = []
  if request.method == 'POST':
    form = DataUploadForm(request.POST, request.FILES)
    if form.is_valid():
      # handle the queries form
      if 'queries_file' in request.FILES:
        query_count = 0
        for line in request.FILES['queries_file']:
          splits = line.strip().split(':')
          if len(splits) != 2:
            continue
          # make sure we don't already have a query with this qid
          if (Query.objects.filter(qid=splits[0]).count() > 0):
            continue
          q = Query(qid = splits[0], text = splits[1])
          q.save()
          query_count += 1
        messages.append('Uploaded %d queries' % query_count)
      if 'document_pairs_file' in request.FILES:
        docpair_count = 0
        missing_queries = set()
        for line in request.FILES['document_pairs_file']:
          splits = line.strip().split(':')
          if len(splits) != 3 or splits[0] in missing_queries:
            continue
          try:
            q = Query.objects.get(qid=splits[0])
          except Query.DoesNotExist:
            missing_queries.add(splits[0])
            messages.append(
              'Query "%s" in Doc Pairs File does not exist' % splits[0])
          # TODO: check for duplicates
          docpair = QueryDocumentPair(query = q,
                                      left_doc = splits[1],
                                      right_doc = splits[2])
          docpair.save()
          docpair_count += 1
        messages.append('Uploaded %d query docpairs' % docpair_count)
  else:
    form = DataUploadForm()
  return render_to_response('assessment/upload_data.html',
                            {'messages': messages, 'form': form},
                            RequestContext(request))

@login_required
def assessor_dashboard(request):
  # assignments ordered in decreasing order of # of pending assessments
  assignments = list(request.user.assignments.all())
  assignments.sort(key=lambda a: a.num_assessments_pending(), reverse=True)

  # need queries not assigned to this user that have pending assignments.
  # We'll find a random set of 5.
  # TODO: filter queries that have pending assignments
  assigned_query_ids = [ a.query.id for a in assignments ]
  available_queries = \
    Query.objects.exclude(id__in=assigned_query_ids)\
      .filter(remaining_assignments__gt=0).order_by('?')[:5]

  # comment form
  comment_form = CommentForm()

  data = { 'assignments': assignments, 'available_queries': available_queries,
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
    assignment.save()
    # decrement our remaining_assignments field
    query.remaining_assignments -= 1
    query.save()
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

  return render_to_response('assessment/assignment_detail.html',
    {'assignment': a}, RequestContext(request))

@login_required
def next_assessment(request, assignment_id):
  assignment = get_object_or_404(Assignment, pk=assignment_id)
  if assignment.assessor != request.user:
    return render_to_response('assessment/access_error.html',
      {'message': 'Sorry, you don\'t have permission to view this assignment'},
      RequestContext(request))

  if assignment.complete():
    return HttpResponseRedirect(reverse('assignment_detail',
                                args=[assignment.id]))

  # Get a random query-doc pair
  query_doc_pair = assignment.pending_query_doc_pairs().order_by('?')[0]
  # Redirect to the new_assessment page
  return HttpResponseRedirect(reverse('new_assessment',
    args=[assignment.id, query_doc_pair.id]))

@login_required
def new_assessment(request, assignment_id, querydocumentpair_id):
  assignment = get_object_or_404(Assignment, pk=assignment_id)
  if assignment.assessor != request.user:
    return render_to_response('assessment/access_error.html',
      {'message': 'Sorry, you don\'t have permission to view this assignment'},
      RequestContext(request))

  query_doc_pair = get_object_or_404(QueryDocumentPair, pk=querydocumentpair_id)
  if query_doc_pair.query != assignment.query:
    return render_to_response('assessment/access_error.html',
      {'message': 'Queries don\'t match (%s != %s)' % \
                    (query_doc_pair.query, assignment.query) },
      RequestContext(request))

  if request.method == 'POST':
    form = PreferenceAssessmentForm(request.POST)
    reason_form = pref_assessment_form_factory.create(request.POST)
    if form.is_valid() and reason_form.is_valid():
      # create a new assessment
      assessment = PreferenceAssessment(
        assignment = assignment,
        query_doc_pair = query_doc_pair,
        preference = form.cleaned_data['preference'],
        preference_reason_other = reason_form.cleaned_data['other'],
        swap_docs = form.cleaned_data['swap_docs'])
      assessment.save()

      # create possibly many preference reasons
      for reason in reason_form.checked_reasons():
        assessment_reason = PreferenceAssessmentReason(
          assessment = assessment,
          reason = reason)
        assessment_reason.save()

      if '_continue' in request.POST:
        return HttpResponseRedirect(reverse('next_assessment',
                                            args=[assignment.id]))
      elif '_save' in request.POST:
        return HttpResponseRedirect(reverse('assessment_detail',
                                            args=[assessment.id]))
      elif '_complete' in request.POST:
        return HttpResponseRedirect(reverse('dashboard'))

  assessment = PreferenceAssessment(
    query_doc_pair = query_doc_pair,
    swap_docs = app_settings.RANDOMIZE_DOC_PRESENTATION and randint(0,1)==1)
  form = PreferenceAssessmentForm(instance = assessment)
  reason_form = pref_assessment_form_factory.create()

  submit_options = [('Submit', '_save')]
  if assignment.num_assessments_pending() > 1:
    submit_options.append( ('Submit & Continue', '_continue') )
  elif assignment.num_assessments_pending() == 1:
    submit_options.append( ('Submit & Return to Dashboard', '_complete') )

  return render_to_response('assessment/assessment_detail.html',
    {'assignment': assignment,
      'assessment': assessment,
      'form': form, 'reason_form': reason_form,
      'submit_options': submit_options},
    RequestContext(request))


@login_required
def assessment_detail(request, assessment_id):
  '''To handle updating a previously entered assessment'''
  assessment = get_object_or_404(PreferenceAssessment, pk=assessment_id)
  if assessment.assignment.assessor != request.user:
    return render_to_response('assessment/access_error.html',
      {'message': 'Sorry, you don\'t have permission to view this assessment'},
      RequestContext(request))

  if request.method == 'POST':
    form = PreferenceAssessmentForm(request.POST)
    reason_form = pref_assessment_form_factory.create(request.POST)
    if form.is_valid() and reason_form.is_valid():
      assessment.preference = form.cleaned_data['preference']
      assessment.preference_reason_other = reason_form.cleaned_data['other']
      assessment.save()

      # update the checked reasons
      existing_assessment_reasons = assessment.reasons
      existing_ids = set( r.reason.id for r in \
                          existing_assessment_reasons.all() )
      new_reasons = reason_form.checked_reasons()
      new_ids = set( r.id for r in new_reasons )
      # delete existing reasons that aren't checked any more
      for r in existing_assessment_reasons.exclude(reason__id__in=new_ids):
        r.delete()
      # add new ones that aren't in the existing reasons
      for r in new_reasons.exclude(id__in=existing_ids):
        assessment_reason = PreferenceAssessmentReason(
          assessment = assessment,
          reason = r)
        assessment_reason.save()

      if '_continue' in request.POST:
        return HttpResponseRedirect(reverse('next_assessment',
                                            args=[assessment.assignment.id]))
      elif '_save' in request.POST:
        return HttpResponseRedirect(reverse('assessment_detail',
                                            args=[assessment.id]))

  form = PreferenceAssessmentForm(instance = assessment)
  reason_form = pref_assessment_form_factory.create_from_assessment(assessment)

  submit_options = [('Submit', '_save')]
  if assessment.assignment.num_assessments_pending() > 0:
    submit_options.append( ('Submit & Assess More', '_continue') )

  return render_to_response('assessment/assessment_detail.html',
    {'form': form, 'reason_form': reason_form,
      'assessment': assessment,
      'assignment': assessment.assignment,
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
