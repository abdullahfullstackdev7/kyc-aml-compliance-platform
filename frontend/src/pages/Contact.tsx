import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Reveal } from "@/components/Reveal";

export default function Contact() {
  const [submitted, setSubmitted] = useState(false);

  return (
    <div className="container max-w-lg py-16 md:py-24">
      <Reveal>
        <h1 className="font-serif text-4xl font-semibold text-navy dark:text-white">
          Contact sales
        </h1>
        <p className="mt-3 text-neutral-900/70 dark:text-white/70">
          Tell us about your team and we'll follow up.
        </p>

        {submitted ? (
          <div className="mt-8 rounded-card border border-success-green/30 bg-success-green/10 p-6 text-sm text-success-green">
            Thanks &mdash; this is a demo form, no message was actually sent, but in production
            you'd hear back within one business day.
          </div>
        ) : (
          <form
            className="mt-8 space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
              setSubmitted(true);
            }}
          >
            <div>
              <label htmlFor="name" className="text-sm font-medium">
                Name
              </label>
              <input
                id="name"
                required
                className="mt-1 w-full rounded-lg border border-black/10 px-3 py-2 text-sm outline-none focus:border-teal focus:ring-1 focus:ring-teal dark:border-white/20 dark:bg-transparent"
              />
            </div>
            <div>
              <label htmlFor="work-email" className="text-sm font-medium">
                Work email
              </label>
              <input
                id="work-email"
                type="email"
                required
                className="mt-1 w-full rounded-lg border border-black/10 px-3 py-2 text-sm outline-none focus:border-teal focus:ring-1 focus:ring-teal dark:border-white/20 dark:bg-transparent"
              />
            </div>
            <div>
              <label htmlFor="message" className="text-sm font-medium">
                What are you looking to solve?
              </label>
              <textarea
                id="message"
                rows={4}
                required
                className="mt-1 w-full rounded-lg border border-black/10 px-3 py-2 text-sm outline-none focus:border-teal focus:ring-1 focus:ring-teal dark:border-white/20 dark:bg-transparent"
              />
            </div>
            <Button type="submit" className="w-full">
              Send
            </Button>
          </form>
        )}
      </Reveal>
    </div>
  );
}
