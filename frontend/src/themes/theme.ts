export type ThemeMode = 'dark' | 'light';
export type ThemeName = 'default' | 'A' | 'B' | 'C' | 'D';

export interface ThemeConfig {
    brand: {
        primary: string;
        primaryHover: string;
        primarySoft: string;
        secondary: string;
        secondaryHover: string;
        glowPrimary: string;
        glowSecondary: string;
        glowInfo: string;
    };
    neutrals: {
        background: {
            main: string;
            panel: string;
            elevated: string;
            rowHover: string;
            sidebar: string;
        };
        borders: {
            main: string;
            divider: string;
            active: string;
        };
        text: {
            primary: string;
            secondary: string;
            muted: string;
            disabled: string;
        };
    };
    semantic: {
        success: {
            base: string;
            hover: string;
            softBg: string;
        };
        warning: {
            base: string;
            hover: string;
            softBg: string;
        };
        error: {
            base: string;
            hover: string;
            softBg: string;
        };
        info: {
            base: string;
            hover: string;
            softBg: string;
        };
    };
    buttons: {
        primary: {
            bg: string;
            hoverBg: string;
            text: string;
            border: string;
            shadow: string;
            focusRing: string;
        };
        secondary: {
            bg: string;
            hoverBg: string;
            text: string;
            border: string;
            shadow: string;
            focusRing: string;
        };
        tertiary: {
            bg: string;
            hoverBg: string;
            text: string;
            border: string;
            shadow: string;
            focusRing: string;
        };
    };
    cards: {
        standard: {
            bg: string;
            border: string;
            shadow: string;
        };
        hoverable: {
            bg: string;
            hoverBg: string;
            border: string;
            shadow: string;
        };
        highlighted: {
            bg: string;
            border: string;
            glow: string;
            shadow: string;
        };
    };
    inputs: {
        default: {
            bg: string;
            border: string;
            text: string;
            placeholder: string;
        };
        focus: {
            border: string;
            shadow: string;
        };
        disabled: {
            bg: string;
            border: string;
            text: string;
            placeholder: string;
        };
    };
    badges: {
        default: {
            bg: string;
            text: string;
        };
        primary: {
            bg: string;
            text: string;
        };
        secondary: {
            bg: string;
            text: string;
        };
    };
    shadows: {
        soft: string;
        medium: string;
        dialog: string;
    };
}

interface PartialThemeData {
    brand: {
        primary: string;
        primaryHover: string;
        secondary?: string;
        secondaryHover?: string;
    };
    dark: {
        background: {
            main: string;
            panel: string;
            elevated: string;
            rowHover: string;
            sidebar: string;
        };
        borders: {
            main: string;
            divider: string;
            active: string;
        };
        text: {
            primary: string;
            secondary: string;
            muted: string;
            disabled: string;
        };
        semantic: {
            success: {
                base: string;
                hover: string;
                softBg: string;
            };
            warning: {
                base: string;
                hover: string;
                softBg: string;
            };
            error: {
                base: string;
                hover: string;
                softBg: string;
            };
            info: {
                base: string;
                hover: string;
                softBg: string;
            };
        };
    };
    light: {
        background: {
            main: string;
            panel: string;
            elevated: string;
            rowHover: string;
            sidebar: string;
        };
        borders: {
            main: string;
            divider: string;
            active: string;
        };
        text: {
            primary: string;
            secondary: string;
            muted: string;
            disabled: string;
        };
        semantic: {
            success: {
                base: string;
                hover: string;
                softBg: string;
            };
            warning: {
                base: string;
                hover: string;
                softBg: string;
            };
            error: {
                base: string;
                hover: string;
                softBg: string;
            };
            info: {
                base: string;
                hover: string;
                softBg: string;
            };
        };
    };
}

// Helper to convert hex to rgba with opacity
function hexToRgba(hex: string, opacity: number): string {
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    return `rgba(${r}, ${g}, ${b}, ${opacity})`;
}

// Helper to build full ThemeConfig from partial data
function buildThemeConfig(data: PartialThemeData, mode: ThemeMode): ThemeConfig {
    const modeData = mode === 'dark' ? data.dark : data.light;
    const primary = data.brand.primary;
    const primaryHover = data.brand.primaryHover;
    const secondary = data.brand.secondary || primary;
    const secondaryHover = data.brand.secondaryHover || primaryHover;

    // Determine button text color based on mode
    // Dark mode themes typically use dark text on bright primary buttons
    // Light mode themes typically use white text on bright primary buttons
    const buttonText = mode === 'dark' ? modeData.background.main : '#FFFFFF';

    // Determine shadow opacity based on mode
    const shadowOpacity = mode === 'dark' ? 0.5 : 0.08;
    const dialogShadowOpacity = mode === 'dark' ? 0.65 : 0.12;

    return {
        brand: {
            primary,
            primaryHover,
            primarySoft: hexToRgba(primary, 0.6),
            secondary,
            secondaryHover,
            glowPrimary: hexToRgba(primary, 0.30),
            glowSecondary: hexToRgba(secondary, 0.30),
            glowInfo: hexToRgba(modeData.semantic.info.base, 0.25),
        },
        neutrals: modeData,
        semantic: modeData.semantic,
        buttons: {
            primary: {
                bg: primary,
                hoverBg: primaryHover,
                text: buttonText,
                border: 'none',
                shadow: mode === 'dark'
                    ? `0 2px 6px ${hexToRgba(primary, 0.35)}`
                    : `0 2px 6px rgba(0,0,0,0.10)`,
                focusRing: `0 0 0 3px ${hexToRgba(primary, 0.25)}`,
            },
            secondary: {
                bg: mode === 'dark' ? modeData.borders.main : '#FFFFFF',
                hoverBg: mode === 'dark' ? modeData.background.panel : modeData.background.rowHover,
                text: mode === 'dark' ? modeData.text.primary : primary,
                border: `1px solid ${primary}`,
                shadow: mode === 'dark' ? 'none' : '0 1px 2px rgba(0,0,0,0.04)',
                focusRing: `0 0 0 3px ${hexToRgba(primary, 0.25)}`,
            },
            tertiary: {
                bg: 'transparent',
                hoverBg: hexToRgba(primary, 0.08),
                text: primary,
                border: 'none',
                shadow: 'none',
                focusRing: `0 0 0 3px ${hexToRgba(primary, 0.25)}`,
            },
        },
        cards: {
            standard: {
                bg: modeData.background.panel,
                border: modeData.borders.main,
                shadow: `0 2px 6px rgba(0,0,0,${mode === 'dark' ? 0.30 : 0.05})`,
            },
            hoverable: {
                bg: modeData.background.panel,
                hoverBg: modeData.background.elevated,
                border: modeData.borders.main,
                shadow: `0 2px 6px rgba(0,0,0,${mode === 'dark' ? 0.30 : 0.05})`,
            },
            highlighted: {
                bg: modeData.background.panel,
                border: primary,
                glow: hexToRgba(primary, mode === 'dark' ? 0.12 : 0.10),
                shadow: `0 0 0 1px ${primary}`,
            },
        },
        inputs: {
            default: {
                bg: mode === 'dark' ? modeData.background.rowHover : modeData.background.panel,
                border: modeData.borders.divider,
                text: modeData.text.primary,
                placeholder: modeData.text.muted,
            },
            focus: {
                border: primary,
                shadow: `0 0 0 2px ${hexToRgba(primary, 0.25)}`,
            },
            disabled: {
                bg: mode === 'dark' ? modeData.background.main : modeData.background.rowHover,
                border: modeData.borders.main,
                text: modeData.text.disabled,
                placeholder: modeData.text.disabled,
            },
        },
        badges: {
            default: {
                bg: mode === 'dark' ? modeData.borders.main : modeData.background.rowHover,
                text: modeData.text.primary,
            },
            primary: {
                bg: primary,
                text: buttonText,
            },
            secondary: {
                bg: secondary,
                text: buttonText,
            },
        },
        shadows: {
            soft: `0 1px 2px rgba(0,0,0,${mode === 'dark' ? 0.40 : 0.04})`,
            medium: `0 2px 6px rgba(0,0,0,${shadowOpacity})`,
            dialog: `0 4px ${mode === 'dark' ? '14px' : '12px'} rgba(0,0,0,${dialogShadowOpacity})`,
        },
    };
}

// Default theme (original)
const defaultThemeData: PartialThemeData = {
    brand: {
        primary: '#FF7A18',
        primaryHover: '#FF9E40',
        secondary: '#8A63FF',
        secondaryHover: '#B39CFF',
    },
    dark: {
        background: {
            main: '#111214',
            panel: '#181A1D',
            elevated: '#1C1E21',
            rowHover: '#1A1C1F',
            sidebar: '#181A1D',
        },
        borders: {
            main: '#222427',
            divider: '#2C2E31',
            active: '#FF7A18',
        },
        text: {
            primary: '#E6E6E6',
            secondary: '#B8B8B8',
            muted: '#8A8A8A',
            disabled: '#6B6B6B',
        },
        semantic: {
            success: {
                base: '#4BD37B',
                hover: '#6BE598',
                softBg: '#133A23',
            },
            warning: {
                base: '#FFB545',
                hover: '#FFD089',
                softBg: '#3A2E12',
            },
            error: {
                base: '#FF4F61',
                hover: '#FF7A86',
                softBg: '#3A1319',
            },
            info: {
                base: '#58BFFF',
                hover: '#89D2FF',
                softBg: '#11293A',
            },
        },
    },
    light: {
        background: {
            main: '#F8F9FA',
            panel: '#FFFFFF',
            elevated: '#FFFFFF',
            rowHover: '#F0F2F5',
            sidebar: '#FFFFFF',
        },
        borders: {
            main: '#D8D8D8',
            divider: '#E5E5E5',
            active: '#FF7A18',
        },
        text: {
            primary: '#1D1D1D',
            secondary: '#4A4A4A',
            muted: '#7A7A7A',
            disabled: '#BEBEBE',
        },
        semantic: {
            success: {
                base: '#3DBE6C',
                hover: '#56D786',
                softBg: '#E6F7EC',
            },
            warning: {
                base: '#F5A623',
                hover: '#FFC55A',
                softBg: '#FFF4E0',
            },
            error: {
                base: '#E0414D',
                hover: '#FF6B77',
                softBg: '#FCECEF',
            },
            info: {
                base: '#3EA8FF',
                hover: '#6BC3FF',
                softBg: '#E7F4FF',
            },
        },
    },
};

// Theme A
const themeAData: PartialThemeData = {
    brand: {
        primary: '#88C0D0',
        primaryHover: '#A3D7E3',
        secondary: '#BF616A',
        secondaryHover: '#D77C85',
    },
    dark: {
        background: {
            main: '#2E3440',
            panel: '#3B4252',
            elevated: '#3B4252',
            rowHover: '#434C5E',
            sidebar: '#3B4252',
        },
        borders: {
            main: '#434C5E',
            divider: '#4C566A',
            active: '#88C0D0',
        },
        text: {
            primary: '#ECEFF4',
            secondary: '#D8DEE9',
            muted: '#BFC5D0',
            disabled: '#8F9BAA',
        },
        semantic: {
            success: {
                base: '#A3BE8C',
                hover: '#B6D3A4',
                softBg: '#3C4A35',
            },
            warning: {
                base: '#EBCB8B',
                hover: '#F4D9A8',
                softBg: '#4A4233',
            },
            error: {
                base: '#BF616A',
                hover: '#D77C85',
                softBg: '#4A2F35',
            },
            info: {
                base: '#5E81AC',
                hover: '#7EA5D4',
                softBg: '#2E3C4F',
            },
        },
    },
    light: {
        background: {
            main: '#ECEFF4',
            panel: '#FFFFFF',
            elevated: '#FFFFFF',
            rowHover: '#E5E9F0',
            sidebar: '#FFFFFF',
        },
        borders: {
            main: '#D8DEE9',
            divider: '#E5E9F0',
            active: '#88C0D0',
        },
        text: {
            primary: '#2E3440',
            secondary: '#4C566A',
            muted: '#6B758A',
            disabled: '#AEB6C3',
        },
        semantic: {
            success: {
                base: '#A3BE8C',
                hover: '#B6D3A4',
                softBg: '#EEF4E8',
            },
            warning: {
                base: '#EBCB8B',
                hover: '#F4D9A8',
                softBg: '#FDF6E8',
            },
            error: {
                base: '#BF616A',
                hover: '#D77C85',
                softBg: '#F7EDEE',
            },
            info: {
                base: '#5E81AC',
                hover: '#7EA5D4',
                softBg: '#E8F1FA',
            },
        },
    },
};

// Theme B
const themeBData: PartialThemeData = {
    brand: {
        primary: '#00FF9C',
        primaryHover: '#34FFB0',
        secondary: '#00C7FF',
        secondaryHover: '#4AD8FF',
    },
    dark: {
        background: {
            main: '#0B0F0C',
            panel: '#121715',
            elevated: '#161C19',
            rowHover: '#1D2420',
            sidebar: '#121715',
        },
        borders: {
            main: '#1D2420',
            divider: '#232B26',
            active: '#00FF9C',
        },
        text: {
            primary: '#E5FFE9',
            secondary: '#B6E2C2',
            muted: '#8AB39A',
            disabled: '#5A7263',
        },
        semantic: {
            success: {
                base: '#00FF9C',
                hover: '#34FFB0',
                softBg: '#0A261B',
            },
            warning: {
                base: '#FFD800',
                hover: '#FFE54A',
                softBg: '#2E2A0A',
            },
            error: {
                base: '#FF3366',
                hover: '#FF668C',
                softBg: '#3A0F18',
            },
            info: {
                base: '#00C7FF',
                hover: '#4AD8FF',
                softBg: '#0A232E',
            },
        },
    },
    light: {
        background: {
            main: '#F8FFFB',
            panel: '#FFFFFF',
            elevated: '#FFFFFF',
            rowHover: '#EFFDF6',
            sidebar: '#FFFFFF',
        },
        borders: {
            main: '#CFEDE0',
            divider: '#E0F8ED',
            active: '#00FF9C',
        },
        text: {
            primary: '#0D1411',
            secondary: '#32443C',
            muted: '#5C7C6E',
            disabled: '#A8C1B7',
        },
        semantic: {
            success: {
                base: '#00FF9C',
                hover: '#34FFB0',
                softBg: '#E8FFF4',
            },
            warning: {
                base: '#FFD800',
                hover: '#FFE54A',
                softBg: '#FFF9DD',
            },
            error: {
                base: '#FF3366',
                hover: '#FF668C',
                softBg: '#FFE8EE',
            },
            info: {
                base: '#00C7FF',
                hover: '#4AD8FF',
                softBg: '#E8F8FF',
            },
        },
    },
};

// Theme C
const themeCData: PartialThemeData = {
    brand: {
        primary: '#9B5CFF',
        primaryHover: '#B98BFF',
        secondary: '#FF5CF4',
        secondaryHover: '#FF8DF7',
    },
    dark: {
        background: {
            main: '#000000',
            panel: '#0A0A0A',
            elevated: '#121212',
            rowHover: '#1A1A1A',
            sidebar: '#0A0A0A',
        },
        borders: {
            main: '#1A1A1A',
            divider: '#262626',
            active: '#9B5CFF',
        },
        text: {
            primary: '#EDE7F6',
            secondary: '#C8BEE3',
            muted: '#A99EC8',
            disabled: '#6D648A',
        },
        semantic: {
            success: {
                base: '#4BD37B',
                hover: '#6BE598',
                softBg: '#0E2417',
            },
            warning: {
                base: '#FFB83B',
                hover: '#FFCD78',
                softBg: '#2A1E0A',
            },
            error: {
                base: '#FF4F8B',
                hover: '#FF7AA8',
                softBg: '#300F1D',
            },
            info: {
                base: '#8A63FF',
                hover: '#B39CFF',
                softBg: '#1D153A',
            },
        },
    },
    light: {
        background: {
            main: '#F5F0FF',
            panel: '#FFFFFF',
            elevated: '#FFFFFF',
            rowHover: '#EEE7FF',
            sidebar: '#FFFFFF',
        },
        borders: {
            main: '#D6C9F3',
            divider: '#E6DCF8',
            active: '#9B5CFF',
        },
        text: {
            primary: '#2D1B43',
            secondary: '#4D3A66',
            muted: '#7A6C92',
            disabled: '#B8AACD',
        },
        semantic: {
            success: {
                base: '#4BD37B',
                hover: '#6BE598',
                softBg: '#EBF7EF',
            },
            warning: {
                base: '#FFB83B',
                hover: '#FFCD78',
                softBg: '#FFF4E3',
            },
            error: {
                base: '#FF4F8B',
                hover: '#FF7AA8',
                softBg: '#FFE9F1',
            },
            info: {
                base: '#8A63FF',
                hover: '#B39CFF',
                softBg: '#F1EBFF',
            },
        },
    },
};

// Theme D
const themeDData: PartialThemeData = {
    brand: {
        primary: '#FF6A3D',
        primaryHover: '#FF8C67',
        secondary: '#FFA745',
        secondaryHover: '#FFC378',
    },
    dark: {
        background: {
            main: '#171515',
            panel: '#1E1C1C',
            elevated: '#272424',
            rowHover: '#2F2B2B',
            sidebar: '#1E1C1C',
        },
        borders: {
            main: '#2A2626',
            divider: '#332F2F',
            active: '#FF6A3D',
        },
        text: {
            primary: '#F5F1EE',
            secondary: '#CDC5C2',
            muted: '#A69F9C',
            disabled: '#6F6967',
        },
        semantic: {
            success: {
                base: '#52B788',
                hover: '#72CBA2',
                softBg: '#1A2A24',
            },
            warning: {
                base: '#E0A81A',
                hover: '#F0C257',
                softBg: '#2E260C',
            },
            error: {
                base: '#D9534F',
                hover: '#E97C78',
                softBg: '#3A1615',
            },
            info: {
                base: '#3FA3FF',
                hover: '#72C0FF',
                softBg: '#10233A',
            },
        },
    },
    light: {
        background: {
            main: '#FFFAF7',
            panel: '#FFFFFF',
            elevated: '#FFFFFF',
            rowHover: '#FFF2EB',
            sidebar: '#FFFFFF',
        },
        borders: {
            main: '#E7DCD7',
            divider: '#F0E7E3',
            active: '#FF6A3D',
        },
        text: {
            primary: '#2B2321',
            secondary: '#4B403D',
            muted: '#7D716E',
            disabled: '#BBAFAE',
        },
        semantic: {
            success: {
                base: '#52B788',
                hover: '#72CBA2',
                softBg: '#EEF7F3',
            },
            warning: {
                base: '#E0A81A',
                hover: '#F0C257',
                softBg: '#FFF3DD',
            },
            error: {
                base: '#D9534F',
                hover: '#E97C78',
                softBg: '#FCEBEA',
            },
            info: {
                base: '#3FA3FF',
                hover: '#72C0FF',
                softBg: '#EAF5FF',
            },
        },
    },
};

// Build all themes
export const themes: Record<ThemeName, Record<ThemeMode, ThemeConfig>> = {
    default: {
        dark: buildThemeConfig(defaultThemeData, 'dark'),
        light: buildThemeConfig(defaultThemeData, 'light'),
    },
    A: {
        dark: buildThemeConfig(themeAData, 'dark'),
        light: buildThemeConfig(themeAData, 'light'),
    },
    B: {
        dark: buildThemeConfig(themeBData, 'dark'),
        light: buildThemeConfig(themeBData, 'light'),
    },
    C: {
        dark: buildThemeConfig(themeCData, 'dark'),
        light: buildThemeConfig(themeCData, 'light'),
    },
    D: {
        dark: buildThemeConfig(themeDData, 'dark'),
        light: buildThemeConfig(themeDData, 'light'),
    },
};

// Helper to get theme config
export function getThemeConfig(themeName: ThemeName, mode: ThemeMode): ThemeConfig {
    return themes[themeName][mode];
}
