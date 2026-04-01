import { useAuthStore } from '../store/authStore';

export default function PermissionButton({
  code,
  children,
  className = '',
  fallback = null,
  as = 'button',
  ...props
}) {
  const hasPermission = useAuthStore((state) => state.hasPermission);
  const Tag = as;

  if (!hasPermission(code)) {
    return fallback;
  }

  return (
    <Tag className={className} {...props}>
      {children}
    </Tag>
  );
}
