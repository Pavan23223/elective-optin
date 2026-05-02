from django import forms
from .models import Course, CATEGORY_CHOICES


class CourseForm(forms.ModelForm):
    class Meta:
        model = Course
        fields = ['name', 'category', 'semester', 'credits', 'salient_features', 'job_perspective', 'prerequisites', 'seats']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Machine Learning'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'semester': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 8}),
            'credits': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 6}),
            'salient_features': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Key topics covered...'}),
            'job_perspective': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Career roles this course leads to...'}),
            'prerequisites': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Data Structures, or None'}),
            'seats': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
        }
        labels = {
            'salient_features': 'Salient Features',
            'job_perspective': 'Job Perspective',
            'prerequisites': 'Prerequisites',
            'seats': 'Total Seats',
        }


class ExportFilterForm(forms.Form):
    department = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. CSE'}))
    category = forms.ChoiceField(required=False, choices=[('', 'All')] + list(CATEGORY_CHOICES), widget=forms.Select(attrs={'class': 'form-select'}))
    status = forms.ChoiceField(required=False, choices=[('', 'All'), ('allocated', 'Allocated'), ('rejected', 'Rejected'), ('pending', 'Pending')], widget=forms.Select(attrs={'class': 'form-select'}))
