auto_auth {
  method "cert" {
    mount_path = "auth/komodo-webhook"
    config = {
      name        = "komodo-webhook"
      ca_cert     = "/identity/current/ca.crt"
      client_cert = "/identity/current/cert.pem"
      client_key  = "/identity/current/key.pem"
      reload      = true
    }
  }
}

template {
  destination          = "/webhook/signing-secret"
  perms                = "0400"
  backup               = false
  error_on_missing_key = true
  contents = <<EOT
{{- with secret "kv/data/komodo/webhook" -}}
  {{- $value := .Data.data.secret -}}
  {{- if not (sprig_kindIs "string" $value) -}}{{ sprig_fail "Invalid webhook secret type" }}{{- end -}}
  {{- if or (eq $value "") (ne $value (sprig_trim $value)) (sprig_regexMatch "[[:cntrl:]]" $value) -}}
    {{- sprig_fail "Webhook secret must be a nonempty single line without surrounding whitespace" -}}
  {{- end -}}
  {{- $value -}}
{{- end -}}
EOT
}
