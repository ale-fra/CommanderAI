import { AspectRatio, Box, Center, Image, Text } from "@mantine/core";
import type { CardImages } from "../api/types";

export const CARD_RATIO = 488 / 680;

interface CardImageProps {
  name: string;
  images: CardImages;
  back?: boolean;
  radius?: string;
  /** The card name is already visible next to the image (alt text would repeat it). */
  decorative?: boolean;
}

/** A card image at the real card ratio; lazy-loaded, with a text placeholder. */
export function CardImage({
  name,
  images,
  back = false,
  radius = "md",
  decorative = false,
}: CardImageProps) {
  const src = back && images.back ? images.back : images.front;
  return (
    <AspectRatio ratio={CARD_RATIO}>
      {src ? (
        <Image
          src={src}
          alt={decorative ? "" : back ? `${name} (back face)` : name}
          loading="lazy"
          decoding="async"
          radius={radius}
          bg="var(--mantine-color-default-border)"
        />
      ) : (
        <Box
          bg="var(--mantine-color-default-hover)"
          style={{ borderRadius: `var(--mantine-radius-${radius})` }}
        >
          <Center h="100%" p="xs">
            <Text size="sm" ta="center" c="dimmed">
              {name}
            </Text>
          </Center>
        </Box>
      )}
    </AspectRatio>
  );
}
