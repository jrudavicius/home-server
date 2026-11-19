ui = true
disable_mlock = true
api_addr = "https://openbao-server:8200"
cluster_addr = "https://openbao-server:8201"

storage "raft" {
  path    = "/data"
  node_id = "home-1"
}

audit "file" "file" {
  description = "Local OpenBao audit records"
  options {
    file_path = "/audit/audit.json"
  }
}

listener "tcp" {
  address                  = "0.0.0.0:8200"
  tls_cert_file            = "/tls/current/cert.pem"
  tls_key_file             = "/tls/current/key.pem"
  tls_auto_reload          = true
  tls_auto_reload_interval = "10s"
}
