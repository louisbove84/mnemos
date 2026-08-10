{{/*
Chart name, overridable.
*/}}
{{- define "embed.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Fully qualified name. Releasing as "embed" yields resources named "embed", which is
the Service address the ingest chart points MNEMOS_EMBED_BASE_URL at.
*/}}
{{- define "embed.fullname" -}}
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

{{- define "embed.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "embed.labels" -}}
helm.sh/chart: {{ include "embed.chart" . }}
{{ include "embed.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: mnemos
{{- end }}

{{- define "embed.selectorLabels" -}}
app.kubernetes.io/name: {{ include "embed.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}
