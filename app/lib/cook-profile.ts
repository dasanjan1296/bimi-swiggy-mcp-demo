import { create } from "zustand";

export interface CookProfileAnswer {
  questionId: string;
  answer: string | string[] | number | boolean;
  answeredBy: string;
  answeredAt: string;
  confidence: "certain" | "likely" | "unsure";
}

export interface CookProfileVerification {
  memberId: string;
  memberName: string;
  questionId: string;
  agrees: boolean | null;
  correction?: string;
  additions?: string[];
  timestamp: string;
}

export interface CookProfileQuestion {
  id: string;
  section: "basics" | "schedule" | "skills" | "preferences" | "logistics";
  question: string;
  hint: string;
  type: "text" | "number" | "multiselect" | "select" | "yesno" | "chips";
  options?: string[];
  required: boolean;
  cookField?: string;
}

export const COOK_INTERVIEW_QUESTIONS: CookProfileQuestion[] = [
  // Basics
  { id: "name", section: "basics", question: "What's the cook's name?", hint: "What does everyone call her/him?", type: "text", required: true, cookField: "name" },
  { id: "phone", section: "basics", question: "WhatsApp number?", hint: "This is how Bimi will communicate with them", type: "text", required: true, cookField: "whatsappNumber" },
  { id: "experience", section: "basics", question: "How many years of cooking experience?", hint: "Roughly — doesn't need to be exact", type: "number", required: false },
  { id: "languages", section: "basics", question: "What languages does the cook speak?", hint: "This helps Bimi communicate better", type: "chips", options: ["Hindi", "English", "Kannada", "Tamil", "Telugu", "Bengali", "Marathi", "Gujarati", "Malayalam", "Punjabi"], required: false },

  // Schedule
  { id: "slot_type", section: "schedule", question: "Morning cook or evening cook?", hint: "Some cooks come twice — pick the primary slot", type: "select", options: ["Morning", "Evening", "Both"], required: true },
  { id: "arrival", section: "schedule", question: "What time do they arrive?", hint: "e.g., 7:00 PM or 8:00 AM", type: "text", required: true },
  { id: "departure", section: "schedule", question: "What time do they leave?", hint: "e.g., 8:00 PM or 9:00 AM", type: "text", required: true },
  { id: "working_days", section: "schedule", question: "Which days do they work?", hint: "Tap to toggle each day", type: "chips", options: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"], required: true },
  { id: "sunday_off", section: "schedule", question: "Do they take Sundays off?", hint: "Most cooks in India do", type: "yesno", required: false },

  // Skills
  { id: "cuisines", section: "skills", question: "What cuisines are they best at?", hint: "Pick all that apply", type: "chips", options: ["North Indian", "South Indian", "Chinese/Indo-Chinese", "Continental", "Bengali", "Rajasthani", "Gujarati", "Mughlai", "Street Food", "Baking"], required: false },
  { id: "dishes", section: "skills", question: "What are their best dishes?", hint: "The dishes everyone loves — add as many as you want", type: "chips", options: ["Dal Tadka", "Rajma", "Chole", "Aloo Gobi", "Paneer Butter Masala", "Roti", "Paratha", "Poha", "Biryani", "Khichdi", "Egg Curry", "Kadhi", "Pulao", "Dosa", "Idli", "Mix Veg"], required: true, cookField: "repertoire" },
  { id: "new_dishes", section: "skills", question: "Are they open to learning new recipes?", hint: "If yes, Bimi can share YouTube recipe links", type: "yesno", required: false },
  { id: "cooking_style", section: "skills", question: "How would you describe their cooking?", hint: "This helps Bimi suggest the right meals", type: "chips", options: ["Home-style comfort", "Restaurant-quality", "Health-conscious", "Quick & efficient", "Traditional", "Experimental", "Spicy", "Mild"], required: false },

  // Preferences
  { id: "cook_diet", section: "preferences", question: "Does the cook have dietary restrictions?", hint: "Some cooks won't handle non-veg, onion, garlic, etc.", type: "chips", options: ["Vegetarian only", "No beef", "No pork", "No onion/garlic", "Jain", "None"], required: false, cookField: "dietaryRestrictions" },
  { id: "brands", section: "preferences", question: "Any brand preferences for staples?", hint: "e.g., Aashirvaad Atta, Fortune Oil — the cook often knows best", type: "text", required: false },

  // Logistics
  { id: "pay_day", section: "logistics", question: "When is salary day?", hint: "Day of the month (1-31)", type: "number", required: false, cookField: "payDay" },
  { id: "salary", section: "logistics", question: "Monthly salary?", hint: "In ₹ — helps track payments", type: "number", required: false, cookField: "salary" },
  { id: "monthly_leaves", section: "logistics", question: "How many days off per month?", hint: "Typical: 4 (one per week)", type: "number", required: false, cookField: "monthlyLeaves" },
  { id: "has_key", section: "logistics", question: "Do they have a house key?", hint: "Can they enter and start cooking if nobody is home?", type: "yesno", required: false },
  { id: "payment_method", section: "logistics", question: "How do you pay them?", hint: "Helps with salary tracking", type: "select", options: ["Cash", "UPI/GPay", "Bank transfer", "Mixed"], required: false },
];

export const SECTION_META: Record<string, { label: string; icon: string; description: string }> = {
  basics: { label: "The Basics", icon: "person-circle", description: "Name, contact, background" },
  schedule: { label: "Schedule", icon: "time-outline", description: "When do they come?" },
  skills: { label: "What They Cook", icon: "restaurant-outline", description: "Dishes, cuisines, style" },
  preferences: { label: "Their Preferences", icon: "heart-outline", description: "Restrictions and brand choices" },
  logistics: { label: "Pay & Leave", icon: "cash-outline", description: "Salary, leaves, logistics" },
};

interface CookProfileStore {
  answers: CookProfileAnswer[];
  verifications: CookProfileVerification[];
  interviewComplete: boolean;
  verificationComplete: boolean;

  setAnswer: (questionId: string, answer: string | string[] | number | boolean, answeredBy: string, confidence?: "certain" | "likely" | "unsure") => void;
  addVerification: (v: Omit<CookProfileVerification, "timestamp">) => void;
  /** Remove a single member's verification for a question (used by the "Change" undo affordance). */
  removeVerification: (memberId: string, questionId: string) => void;
  markInterviewComplete: () => void;
  markVerificationComplete: () => void;
  getAnswer: (questionId: string) => CookProfileAnswer | undefined;
  getVerifications: (questionId: string) => CookProfileVerification[];
  getVerificationSummary: (questionId: string) => { agrees: number; disagrees: number; total: number };
  reset: () => void;
}

export const useCookProfileStore = create<CookProfileStore>((set, get) => ({
  answers: [],
  verifications: [],
  interviewComplete: false,
  verificationComplete: false,

  setAnswer: (questionId, answer, answeredBy, confidence = "certain") =>
    set((state) => ({
      answers: [
        ...state.answers.filter((a) => a.questionId !== questionId),
        { questionId, answer, answeredBy, answeredAt: new Date().toISOString(), confidence },
      ],
    })),

  addVerification: (v) =>
    set((state) => ({
      verifications: [
        ...state.verifications.filter((vf) => !(vf.memberId === v.memberId && vf.questionId === v.questionId)),
        { ...v, timestamp: new Date().toISOString() },
      ],
    })),

  removeVerification: (memberId, questionId) =>
    set((state) => ({
      verifications: state.verifications.filter(
        (v) => !(v.memberId === memberId && v.questionId === questionId),
      ),
    })),

  markInterviewComplete: () => set({ interviewComplete: true }),
  markVerificationComplete: () => set({ verificationComplete: true }),

  getAnswer: (questionId) => get().answers.find((a) => a.questionId === questionId),
  getVerifications: (questionId) => get().verifications.filter((v) => v.questionId === questionId),

  getVerificationSummary: (questionId) => {
    const vs = get().verifications.filter((v) => v.questionId === questionId && v.agrees !== null);
    return { agrees: vs.filter((v) => v.agrees).length, disagrees: vs.filter((v) => !v.agrees).length, total: vs.length };
  },

  reset: () => set({ answers: [], verifications: [], interviewComplete: false, verificationComplete: false }),
}));
