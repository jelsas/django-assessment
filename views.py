from assessment.models import *
from assessment.forms import *
from django.core.urlresolvers import reverse
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render_to_response, \
                             get_object_or_404
from django.contrib.auth.decorators import login_required
from django.template import RequestContext
from django.db.models import Sum
from random import randint

pref_assessment_form_factory = PreferenceAssessmentReasonFormFactory()

def redirect_to_pagename(request, pagename):
  return HttpResponseRedirect(reverse(pagename))

class GlobalAssessmentStatus(object):
  '''Helper class to handle progress reporting'''
  #TODO: break this out into its own module?
  def current_assignments(self):
    return Assignment.objects.count()

  def complete_assignments(self):
    return sum( 1 for a in Assignment.objects.all() if a.complete() )

  def pending_assignments(self):
    return Query.objects.aggregate(
      Sum('remaining_assignments'))['remaining_assignments__sum']

  def assignment_status_chart_arg(self):
    complete = self.complete_assignments()
    assigned_incomplete = self.current_assignments() - complete
    unassigned = self.pending_assignments()
    # scale to 100 max for all of them
    total = complete + assigned_incomplete + unassigned
    if total > 0:
      complete_scaled = 100 * complete / total
      assigned_incomplete_scaled = 100 * assigned_incomplete / total
      unassigned_scaled = 100 * unassigned / total
      return '%d|%d|%d' % \
        (complete_scaled, assigned_incomplete_scaled, unassigned_scaled)
    else:
      return '0|0|100'

  def complete_assessments(self):
    return PreferenceAssessment.objects.count()

  def pending_assessments_assigned(self):
    return sum( a.num_assessments_pending() for a in Assignment.objects.all() )

  def pending_assessments_unassigned(self):
    return sum( (q.remaining_assignments * q.doc_pairs.count()) \
      for q in Query.objects.filter(remaining_assignments__gt=0).all() )

  def assessment_status_chart_arg(self):
    complete = self.complete_assessments()
    assigned_incomplete = self.pending_assessments_assigned()
    unassigned = self.pending_assessments_unassigned()
    # scale to 100 max for all of them
    total = complete + assigned_incomplete + unassigned
    if total > 0:
      complete_scaled = 100 * complete / total
      assigned_incomplete_scaled = 100 * assigned_incomplete / total
      unassigned_scaled = 100 * unassigned / total
      return '%d|%d|%d' % \
        (complete_scaled, assigned_incomplete_scaled, unassigned_scaled)
    else:
      return '0|0|0'

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

  # if this is a superuser, also add the global status stuff
  if request.user.is_superuser:
    data['status'] = GlobalAssessmentStatus()

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
    swap_docs = settings.RANDOMIZE_DOC_PRESENTATION and randint(0,1)==1)
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
