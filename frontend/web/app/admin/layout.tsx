import Link from "next/link";
import { redirect } from "next/navigation";
import { getServerSession } from "next-auth";

export default async function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const session = await getServerSession();

  // Check if user is admin/owner
  if (!session?.user?.isAdmin && !session?.user?.isOwner) {
    redirect("/dashboard");
  }

  return (
    <div className="flex min-h-screen bg-gray-100">
      {/* Sidebar */}
      <aside className="w-64 bg-white shadow-md">
        <div className="p-6">
          <h1 className="text-2xl font-bold text-gray-800">Admin Portal</h1>
          <p className="text-sm text-gray-500 mt-1">
            {session?.user?.isOwner ? "Owner" : "Admin"}
          </p>
        </div>

        <nav className="mt-6">
          <AdminNavLink href="/admin/users" icon="👥">
            Users
          </AdminNavLink>
          <AdminNavLink href="/admin/devices" icon="📱">
            Devices
          </AdminNavLink>
          <AdminNavLink href="/admin/billing" icon="💳">
            Billing
          </AdminNavLink>
          <AdminNavLink href="/admin/analytics" icon="📊">
            Analytics
          </AdminNavLink>
          <AdminNavLink href="/admin/fraud" icon="🚨">
            Fraud
          </AdminNavLink>
          <AdminNavLink href="/admin/support" icon="💬">
            Support
          </AdminNavLink>
          <AdminNavLink href="/admin/kb" icon="📚">
            Knowledge Base
          </AdminNavLink>
        </nav>

        <div className="absolute bottom-0 w-64 p-6 border-t">
          <Link
            href="/dashboard"
            className="text-sm text-gray-600 hover:text-gray-900"
          >
            ← Back to Dashboard
          </Link>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 p-8">{children}</main>
    </div>
  );
}

function AdminNavLink({
  href,
  icon,
  children,
}: {
  href: string;
  icon: string;
  children: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      className="flex items-center px-6 py-3 text-gray-700 hover:bg-gray-50 hover:text-gray-900 transition-colors"
    >
      <span className="mr-3 text-xl">{icon}</span>
      <span>{children}</span>
    </Link>
  );
}
