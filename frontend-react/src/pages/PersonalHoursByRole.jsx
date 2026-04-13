import { ROLES } from '../constants/roles';
import { useAuthStore } from '../store/authStore';
import PersonalHoursAdmin from './PersonalHoursAdmin';
import PersonalHoursEmployee from './PersonalHoursEmployee';

export default function PersonalHoursByRole() {
  const user = useAuthStore((state) => state.user);
  const isAdminView = user?.role === ROLES.ADMIN || user?.role === ROLES.MANAGER;
  return isAdminView ? <PersonalHoursAdmin /> : <PersonalHoursEmployee />;
}
