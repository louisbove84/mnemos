{{/*
Chart name, overridable.
*/}}
{{- define "llm.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Fully qualified name. Releasing as "llm" yields resources named "llm", which keeps
the Service address stable for the smoke-test runbook.
*/}}
{{- define "llm.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{- define "llm.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "llm.labels" -}}
helm.sh/chart: {{ include "llm.chart" . }}
{{ include "llm.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: mnemos
{{- end }}

{{- define "llm.selectorLabels" -}}
app.kubernetes.io/name: {{ include "llm.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Absolute path to the weights inside the container.
*/}}
{{- define "llm.modelPath" -}}
{{- printf "/models/%s" .Values.model.file }}
{{- end }}
