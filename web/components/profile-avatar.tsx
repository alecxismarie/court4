import { UserRound } from "lucide-react";

import type { PlayerProfile } from "@/lib/player-profile";
import { cn } from "@/lib/utils";

export function ProfileAvatar({
  profile,
  className,
}: {
  profile: PlayerProfile;
  className?: string;
}) {
  const initials = profileInitials(profile.displayName);
  return (
    <span
      role="img"
      aria-label={
        profile.displayName ? `${profile.displayName} profile photo` : "Player profile photo"
      }
      className={cn(
        "grid shrink-0 place-items-center overflow-hidden rounded-full border-2 border-court-lime bg-court-panel font-semibold text-court-navy",
        className,
      )}
    >
      {profile.profileImageDataUrl ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={profile.profileImageDataUrl}
          alt=""
          className="h-full w-full object-cover"
        />
      ) : initials ? (
        initials
      ) : (
        <UserRound className="h-1/2 w-1/2" />
      )}
    </span>
  );
}

function profileInitials(displayName: string): string {
  return displayName
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part.charAt(0).toUpperCase())
    .join("");
}
