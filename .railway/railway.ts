import { defineRailway, project, service } from "railway/iac";

export const partial = "api";

export default defineRailway(() => {
  const api = service("api", {
    healthcheck: "/health",
    healthcheckTimeout: 30,
  });

  return project("assessorai-dados", {
    resources: [api],
  });
});
