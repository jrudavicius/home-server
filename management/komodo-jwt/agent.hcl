auto_auth {
  method "cert" {
    mount_path = "auth/komodo-jwt"
    config = {
      name        = "komodo-jwt"
      ca_cert     = "/identity/current/ca.crt"
      client_cert = "/identity/current/cert.pem"
      client_key  = "/identity/current/key.pem"
      reload      = true
    }
  }
}

template {
  destination          = "/session/core.config.json"
  perms                = "0400"
  backup               = false
  error_on_missing_key = true
  contents = <<EOT
{{- with secret "kv/data/komodo/jwt" -}}
  {{- $value := .Data.data.secret -}}
  {{- if or (not (sprig_kindIs "string" $value)) (not $value) -}}
    {{- sprig_fail "Session signing key must be a nonempty string" -}}
  {{- end -}}
  {"jwt_secret":{{ $value | toJSON }}}
{{- end -}}
EOT
}
