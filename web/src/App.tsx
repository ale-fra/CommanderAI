import {
  ActionIcon,
  AppShell,
  Badge,
  Burger,
  Center,
  Group,
  Loader,
  NavLink,
  Text,
  Title,
  Tooltip,
  UnstyledButton,
  useComputedColorScheme,
  useMantineColorScheme,
} from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import {
  IconBooks,
  IconCards,
  IconCrown,
  IconHammer,
  IconInfoCircle,
  IconMoon,
  IconSun,
} from "@tabler/icons-react";
import { lazy, Suspense, useEffect } from "react";
import { Navigate, Route, NavLink as RouterNavLink, Routes, useLocation } from "react-router";
import { useStatus } from "./api/queries";
import { CollectionSelect } from "./components/CollectionSelect";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { EmptyState } from "./components/Feedback";

const CollectionPage = lazy(() => import("./pages/CollectionPage"));
const CommandersPage = lazy(() => import("./pages/CommandersPage"));
const BuildPage = lazy(() => import("./pages/BuildPage"));
const DecksPage = lazy(() => import("./pages/DecksPage"));
const DeckDetailPage = lazy(() => import("./pages/DeckDetailPage"));
const ComparePage = lazy(() => import("./pages/ComparePage"));
const AboutPage = lazy(() => import("./pages/AboutPage"));

const NAV = [
  { to: "/collection", label: "Collection", icon: IconCards },
  { to: "/commanders", label: "Commanders", icon: IconCrown },
  { to: "/build", label: "Build", icon: IconHammer },
  { to: "/decks", label: "Decks", icon: IconBooks },
] as const;

function ThemeToggle() {
  const { setColorScheme } = useMantineColorScheme();
  const scheme = useComputedColorScheme("dark");
  const next = scheme === "dark" ? "light" : "dark";
  return (
    <Tooltip label={`Switch to ${next} theme`}>
      <ActionIcon
        variant="default"
        size="lg"
        aria-label={`Switch to ${next} theme`}
        onClick={() => setColorScheme(next)}
      >
        {scheme === "dark" ? <IconSun size={18} /> : <IconMoon size={18} />}
      </ActionIcon>
    </Tooltip>
  );
}

function StatusBadge() {
  const { data, isError } = useStatus();
  if (isError)
    return (
      <Badge color="red" variant="light">
        API offline
      </Badge>
    );
  if (!data) return null;
  return (
    <Tooltip label={`${data.catalog.cards} cards in the catalog · v${data.version}`}>
      <Badge color={data.offline ? "gray" : "teal"} variant="light" visibleFrom="md">
        {data.offline ? "Offline" : "Online"}
      </Badge>
    </Tooltip>
  );
}

function PageFallback() {
  return (
    <Center py="xl">
      <Loader aria-label="Loading page" />
    </Center>
  );
}

export function App() {
  const [opened, { toggle, close }] = useDisclosure();
  const location = useLocation();

  // On navigation: close the mobile menu and start at the top of the new page.
  // biome-ignore lint/correctness/useExhaustiveDependencies: run on route change only
  useEffect(() => {
    close();
    window.scrollTo({ top: 0 });
  }, [location.pathname]);

  return (
    <AppShell
      header={{ height: 60 }}
      navbar={{ width: 220, breakpoint: "sm", collapsed: { mobile: !opened } }}
      padding="md"
    >
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between" wrap="nowrap" gap="sm">
          <Group gap="sm" wrap="nowrap">
            <Burger
              opened={opened}
              onClick={toggle}
              hiddenFrom="sm"
              size="sm"
              aria-label="Toggle navigation"
            />
            <UnstyledButton
              component={RouterNavLink}
              to="/collection"
              aria-label="CommanderAI home"
            >
              <Title order={1} fz="lg" style={{ whiteSpace: "nowrap" }}>
                Commander
                <Text span inherit className="brand-text">
                  AI
                </Text>
              </Title>
            </UnstyledButton>
          </Group>
          <Group gap="xs" wrap="nowrap">
            <Group visibleFrom="sm">
              <CollectionSelect />
            </Group>
            <StatusBadge />
            <ThemeToggle />
          </Group>
        </Group>
      </AppShell.Header>

      <AppShell.Navbar p="sm" aria-label="Main navigation">
        <Group hiddenFrom="sm" mb="sm">
          <CollectionSelect w="100%" />
        </Group>
        {NAV.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            component={RouterNavLink}
            to={to}
            label={label}
            leftSection={<Icon size={18} stroke={1.6} />}
            active={location.pathname.startsWith(to)}
            style={{ borderRadius: "var(--mantine-radius-md)" }}
          />
        ))}
        <NavLink
          component={RouterNavLink}
          to="/about"
          label="About"
          leftSection={<IconInfoCircle size={18} stroke={1.6} />}
          active={location.pathname === "/about"}
          mt="auto"
          style={{ borderRadius: "var(--mantine-radius-md)" }}
        />
      </AppShell.Navbar>

      <AppShell.Main>
        <ErrorBoundary resetKey={location.pathname}>
          <Suspense fallback={<PageFallback />}>
            <Routes>
              <Route path="/" element={<Navigate to="/collection" replace />} />
              <Route path="/collection" element={<CollectionPage />} />
              <Route path="/commanders" element={<CommandersPage />} />
              <Route path="/build" element={<BuildPage />} />
              <Route path="/decks" element={<DecksPage />} />
              <Route path="/decks/compare" element={<ComparePage />} />
              <Route path="/decks/:id" element={<DeckDetailPage />} />
              <Route path="/about" element={<AboutPage />} />
              <Route
                path="*"
                element={
                  <EmptyState title="Page not found">
                    This page does not exist. Use the navigation on the left.
                  </EmptyState>
                }
              />
            </Routes>
          </Suspense>
        </ErrorBoundary>
      </AppShell.Main>
    </AppShell>
  );
}
