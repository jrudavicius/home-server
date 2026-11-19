auto_auth {
  method "cert" {
    mount_path = "auth/openbao-backup"
    config = {
      name        = "openbao-backup"
      ca_cert     = "/identity/current/ca.crt"
      client_cert = "/identity/current/cert.pem"
      client_key  = "/identity/current/key.pem"
      reload      = true
    }
  }
  sink "file" {
    config = {
      path = "/session/token"
      mode = 0400
    }
  }
}
