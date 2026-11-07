import "@mantine/core/styles.css";
import "@mantine/charts/styles.css";
import "@mantine/notifications/styles.css";
import "./styles/fonts.css";
import "./styles/global.css";

import { localStorageColorSchemeManager, MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router";
import { App } from "./App";
import { CardDetailProvider } from "./components/CardDetail";
import { ActiveCollectionProvider } from "./state/ActiveCollection";
import { cssVariablesResolver, theme } from "./theme";

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000, retry: 1, refetchOnWindowFocus: false } },
});

const colorSchemeManager = localStorageColorSchemeManager({ key: "mantine-color-scheme-value" });

const root = document.getElementById("root");
if (!root) throw new Error("#root element missing");

createRoot(root).render(
  <StrictMode>
    <MantineProvider
      theme={theme}
      defaultColorScheme="dark"
      colorSchemeManager={colorSchemeManager}
      cssVariablesResolver={cssVariablesResolver}
    >
      <Notifications position="bottom-right" />
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <ActiveCollectionProvider>
            <CardDetailProvider>
              <App />
            </CardDetailProvider>
          </ActiveCollectionProvider>
        </BrowserRouter>
      </QueryClientProvider>
    </MantineProvider>
  </StrictMode>,
);
