import {
  BarChart3,
  CloudUpload,
  LineChart,
  MapPin,
  ScanSearch,
  Share2,
  TrendingUp,
  UsersRound,
  Video,
} from "lucide-react";

export const landingBenefits = [
  {
    title: "Understand Your Game",
    description: "Movement and positioning insights",
    icon: ScanSearch,
  },
  {
    title: "Track Real Progress",
    description: "See how your performance changes over time",
    icon: TrendingUp,
  },
  {
    title: "Share & Learn",
    description: "Bring match insights into conversations with coaches, partners, and teammates",
    icon: Share2,
  },
] as const;

export const journeySteps = [
  {
    number: 1,
    title: "Upload",
    copy: "Upload a match video you recorded with permission from visible participants.",
    icon: CloudUpload,
  },
  {
    number: 2,
    title: "Review",
    copy: "Court4 checks recording suitability and helps identify the court.",
    icon: Video,
  },
  {
    number: 3,
    title: "Select",
    copy: "Review discovered player candidates and select the player to analyze.",
    icon: UsersRound,
  },
  {
    number: 4,
    title: "Insights",
    copy: "Generate evidence-led movement and positioning results when video quality permits.",
    icon: BarChart3,
  },
  {
    number: 5,
    title: "Improve",
    copy: "Review analysis and play history without fabricated point-level claims.",
    icon: LineChart,
  },
] as const;

export const footerGroups = [
  {
    title: "Product",
    links: [
      { label: "Features", href: "#features" },
      { label: "How It Works", href: "#journey" },
      { label: "Pricing", href: "#alpha-status" },
    ],
  },
  {
    title: "For Clubs",
    links: [
      { label: "Smart Courts", href: "#partner-clubs" },
      { label: "Partner Program", href: "#partner-clubs" },
      { label: "Resources", href: "#newsletter" },
    ],
  },
  {
    title: "Company",
    links: [
      { label: "About Us", href: "#about" },
      { label: "Careers", href: "#newsletter" },
      { label: "Contact", href: "#support" },
    ],
  },
  {
    title: "Support",
    links: [
      { label: "Help Center", href: "#support" },
      { label: "Privacy Policy", href: "/privacy" },
      { label: "Terms of Service", href: "/terms" },
    ],
  },
] as const;

export const mapPins = [
  { left: "26%", top: "22%" },
  { left: "15%", top: "62%" },
  { left: "52%", top: "64%" },
  { left: "79%", top: "39%" },
  { left: "70%", top: "87%" },
] as const;

export { MapPin };
