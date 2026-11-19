auto_auth {
  method "approle" {
    mount_path = "auth/approle"
    config = {
      role_id_file_path                   = "/identity/role-id"
      secret_id_file_path                 = "/identity/secret-id"
      remove_secret_id_file_after_reading = false
    }
  }
}

template {
  source               = "/config/service.ctmpl"
  destination          = "/run/issued/service.conf"
  perms                = "0600"
  backup               = false
  error_on_missing_key = true
}
