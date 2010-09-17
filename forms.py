from django import forms
from django.utils.safestring import mark_safe
from django.utils.encoding import force_unicode
from assessment.models import *
from assessment import app_settings
from registration.forms import RegistrationFormUniqueEmail

class CustomRadioRenderer(forms.widgets.RadioFieldRenderer):
  # see http://skyl.org/log/post/skyl/2010/01/subclass-django-forms-widgets-radiofieldrenderer-and-django-forms-widgets-radioselect-for-custom-rendering-of-individual-choices/
  def render(self):
    """Outputs a <ul> for this set of radio fields."""
    if not app_settings.COLLECT_PREFERENCE_REASON:
      # automatically submits when we're not collecting "why"
      self.attrs['onclick'] = 'this.form.submit()'
    return mark_safe(u'<ul>\n%s\n</ul>' % \
      u'\n'.join([u'<li id="%s">%s</li>' \
        % ('radio_container_%s'%w.index, force_unicode(w) ) for w in self]))


class ValidKeyRegistrationForm(RegistrationFormUniqueEmail):
  registration_key = forms.CharField()

  def clean_registration_key(self):
    if app_settings.REGISTRATION_KEY is not None and \
        self.cleaned_data['registration_key'] != app_settings.REGISTRATION_KEY:
      raise forms.ValidationError(("Incorrect registration key."))
    return self.cleaned_data['registration_key']

class CommentForm(forms.Form):
  message = forms.CharField(widget=forms.Textarea(attrs={'rows':'4'}))

class InformationNeedForm(forms.ModelForm):
  class Meta:
    model = Assignment
    fields = ('description', 'narrative')

class DataUploadForm(forms.Form):
  queries_file = forms.FileField(required=False)
  document_pairs_file = forms.FileField(required=False)

class PreferenceAssessmentForm(forms.Form):
  preference = forms.ChoiceField(
     choices = ( ('LB', 'Left Bad'),
                 ('L', 'Left Preferred'),
                 ('D', 'Duplicates'),
                 ('R', 'Right Preferred'),
                 ('RB', 'Right Bad') ),
     label = 'Which document do you prefer?',
     widget = forms.RadioSelect( renderer = CustomRadioRenderer ) )
  # the left and right docs refer to the AssessedDocuments (not Documents)
  left_doc = forms.CharField( widget = forms.HiddenInput )
  right_doc = forms.CharField( widget = forms.HiddenInput )

  @classmethod
  def from_assessment(cls, assessment):
    '''Creates a PreferenceAssessmentForm from an AssessedDocumentRelation'''
    if assessment.source_presented_left:
      left_doc = assessment.source_doc.id
      right_doc = assessment.target_doc.id
      if assessment.relation_type == 'P':
        preference = 'L'
      elif assessment.relation_type == 'D':
        preference = 'D'
      elif assessment.relation_type == 'B':
        preference = 'LB'
    else:
      left_doc = assessment.target_doc.id
      right_doc = assessment.source_doc.id
      if assessment.relation_type == 'P':
        preference = 'R'
      elif assessment.relation_type == 'D':
        preference = 'D'
      elif assessment.relation_type == 'B':
        preference = 'RB'

    return cls( {'preference':preference,
                 'left_doc':left_doc,
                 'right_doc':right_doc } )

  def to_assessment(self):
    '''Converts this form to an UNSAVED assessment object.'''
    preference = self.cleaned_data['preference']
    left_doc = AssessedDocument.objects.get(pk=self.cleaned_data['left_doc'])
    right_doc = AssessedDocument.objects.get(pk=self.cleaned_data['right_doc'])
    if preference == 'LB':
      return AssessedDocumentRelation( source_doc = left_doc,
                                      target_doc = right_doc,
                                      relation_type = 'B',
                                      source_presented_left = True )
    elif preference == 'L':
      return AssessedDocumentRelation( source_doc = left_doc,
                                      target_doc = right_doc,
                                      relation_type = 'P',
                                      source_presented_left = True )
    elif preference == 'D':
      return AssessedDocumentRelation( source_doc = left_doc,
                                      target_doc = right_doc,
                                      relation_type = 'D',
                                      source_presented_left = True )
    elif preference == 'R':
      return AssessedDocumentRelation( source_doc = right_doc,
                                      target_doc = left_doc,
                                      relation_type = 'P',
                                      source_presented_left = False )
    elif preference == 'RB':
      return AssessedDocumentRelation( source_doc = right_doc,
                                      target_doc = left_doc,
                                      relation_type = 'B',
                                      source_presented_left = False )
    else:
      # shouldn't happen.
      return None

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
