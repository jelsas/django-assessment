from django import forms
from assessment.models import *

class CommentForm(forms.Form):
  message = forms.CharField(widget=forms.Textarea(attrs={'rows':'4'}))

class InformationNeedForm(forms.ModelForm):
  class Meta:
    model = Assignment
    fields = ('description', 'narrative')

class PreferenceAssessmentForm(forms.ModelForm):
  preference = forms.ChoiceField(
    choices = PreferenceAssessment.PREFERENCE_CHOICES,
    label = 'Which document do you prefer?',
    widget = forms.RadioSelect)
  class Meta:
    model = PreferenceAssessment
    fields = ('preference',)

class PreferenceAssessmentReasonForm(forms.Form):

  def __init__(self, *args, **kwargs):
    reasons = kwargs.pop('reasons')
    checked_reasons = kwargs.pop('checked_reasons', None)
    other = kwargs.pop('other', None)
    super(PreferenceAssessmentReasonForm, self).__init__(*args, **kwargs)
    for (id, name) in reasons.iteritems():
      key = 'reason_%d' % id
      self.fields[key] = forms.BooleanField(required=False, label=name)
      if checked_reasons and id in checked_reasons:
        self.initial[key] = True

    # add 'other' at the end
    self.fields['other'] = forms.CharField(max_length=500, required=False)
    if other: self.initial['other'] = other

  def checked_reasons(self):
    reasons = set()
    for (name, value) in self.cleaned_data.iteritems():
      if name.startswith('reason_') and value:
        reasons.add(int(name.replace('reason_', '')))
    return PreferenceReason.objects.all().filter(id__in=reasons)


class PreferenceAssessmentReasonFormFactory(object):
  def reasons(self):
    reasons = {}
    for r in PreferenceReason.objects.filter(active=True):
      reasons[r.id] = r.short_name
    return reasons

  def create_from_assessment(self, preference_assessment, *args, **kwargs):
    checked_reasons = set(r.reason.id for r in \
                          preference_assessment.reasons.all())
    return PreferenceAssessmentReasonForm(reasons = self.reasons(),
                    checked_reasons = checked_reasons,
                    other = preference_assessment.preference_reason_other,
                    *args, **kwargs)


  def create(self, *args, **kwargs):
    return PreferenceAssessmentReasonForm(reasons = self.reasons(),
                                          *args, **kwargs)
