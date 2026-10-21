{{/* Shared RabbitMQ connection env for frontend and worker */}}
{{- define "skywatch.rabbitmqEnv" -}}
- name: RABBITMQ_HOST
  value: "rabbitmq"
- name: RABBITMQ_PORT
  value: "5672"
- name: RABBITMQ_USER
  valueFrom:
    secretKeyRef:
      name: skywatch-rabbitmq
      key: rabbitmq-username
- name: RABBITMQ_PASSWORD
  valueFrom:
    secretKeyRef:
      name: skywatch-rabbitmq
      key: rabbitmq-password
{{- end }}

{{/* True when the Prometheus Operator CRDs are installed */}}
{{- define "skywatch.serviceMonitorsEnabled" -}}
{{- if and .Values.monitoring.serviceMonitors (.Capabilities.APIVersions.Has "monitoring.coreos.com/v1/ServiceMonitor") }}true{{ end }}
{{- end }}
