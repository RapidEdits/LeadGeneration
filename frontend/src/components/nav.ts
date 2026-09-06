import {
  LayoutDashboard, Users, Building2, Megaphone, Inbox, Workflow,
  BarChart3, Sparkles, Plug, Settings, Linkedin, KanbanSquare, CheckSquare,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  title: string;
  href: string;
  icon: LucideIcon;
  soon?: boolean; // feature lands in a later phase
}

export const NAV: NavItem[] = [
  { title: "Overview", href: "/dashboard", icon: LayoutDashboard },
  { title: "Leads", href: "/leads", icon: Users },
  { title: "Companies", href: "/companies", icon: Building2 },
  { title: "Pipeline", href: "/pipeline", icon: KanbanSquare },
  { title: "Campaigns", href: "/campaigns", icon: Megaphone },
  { title: "Tasks", href: "/tasks", icon: CheckSquare },
  { title: "Inbox", href: "/inbox", icon: Inbox },
  { title: "LinkedIn Tasks", href: "/linkedin", icon: Linkedin },
  { title: "Sequences", href: "/sequences", icon: Workflow, soon: true },
  { title: "Analytics", href: "/analytics", icon: BarChart3, soon: true },
  { title: "AI Copilot", href: "/copilot", icon: Sparkles },
  { title: "Integrations", href: "/integrations", icon: Plug, soon: true },
  { title: "Settings", href: "/settings", icon: Settings },
];
