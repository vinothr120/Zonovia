export interface UserRoleRead {
  id: string;
  role_id: string;
  role_name: string;
  scope_type: "tenant" | "school" | "campus";
  scope_id: string | null;
}

export interface Me {
  id: string;
  email: string;
  phone: string | null;
  status: string;
  mfa_enabled: boolean;
  last_login_at: string | null;
  created_at: string;
  roles: UserRoleRead[];
  is_platform_admin: boolean;
  permissions: string[];
}
