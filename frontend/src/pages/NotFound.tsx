import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <div className="container flex min-h-[60vh] flex-col items-center justify-center py-24 text-center">
      <p className="text-sm font-medium text-teal">404</p>
      <h1 className="mt-2 font-serif text-3xl font-semibold text-navy dark:text-white">
        Page not found
      </h1>
      <Button className="mt-6" asChild>
        <Link to="/">Back to home</Link>
      </Button>
    </div>
  );
}
